import threading
import time
import os
import cv2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# AI Modules
from ai.face_emotion import detect_microexpression
from ai.posture_detection import detect_posture
from ai.multimodal_fusion import fuse_signals
from alerts.alert_manager import trigger_alert
from resqpay.api import router as resqpay_router

app = FastAPI(title="ResQPay AI API")
app.include_router(resqpay_router)

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State
SYSTEM_STATE = {
    "is_running": False,
    "last_alert": None,
    "active_alerts_count": 0,
    "camera_status": "Idle",
    "camera_error": None,
}

state_lock = threading.Lock()
start_lock = threading.Lock()
stop_event = threading.Event()
frame_lock = threading.Lock()
capture_lock = threading.Lock()
latest_frame_jpeg = None
camera_thread = None
active_camera_capture = None
camera_attempt_id = 0
camera_watchdog = None
CAMERA_CONNECT_TIMEOUT_SECONDS = 15
CAMERA_STOP_TIMEOUT_SECONDS = 10


def _set_camera_error(attempt_id, message):
    with state_lock:
        if attempt_id != camera_attempt_id:
            return
        SYSTEM_STATE["is_running"] = False
        SYSTEM_STATE["camera_status"] = "Error"
        SYSTEM_STATE["camera_error"] = message


def _camera_timeout(attempt_id, expected_status, message):
    with state_lock:
        if attempt_id != camera_attempt_id or SYSTEM_STATE["camera_status"] != expected_status:
            return
        SYSTEM_STATE["is_running"] = False
        SYSTEM_STATE["camera_status"] = "Error"
        SYSTEM_STATE["camera_error"] = message
        stop_event.set()


def _open_camera():
    """Open the configured camera using Windows' native capture backend when available."""
    try:
        camera_index = int(os.getenv("RESQPAY_CAMERA_INDEX", "0"))
    except ValueError as exc:
        raise RuntimeError("RESQPAY_CAMERA_INDEX must be a non-negative integer.") from exc
    if camera_index < 0:
        raise RuntimeError("RESQPAY_CAMERA_INDEX must be a non-negative integer.")

    if os.name == "nt":
        return cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(camera_index)


def _release_camera(cap):
    try:
        cap.release()
    except Exception as exc:
        print(f"[ERROR] Could not release camera capture: {exc}")


def monitoring_loop(attempt_id):
    """Initialize, process, and stream frames from a single camera capture."""
    global active_camera_capture, latest_frame_jpeg
    print("[SYSTEM] Monitoring Thread Started...")
    cap = None
    error_message = None

    try:
        cap = _open_camera()
        if not cap.isOpened():
            raise RuntimeError(
                "Could not open the camera. Check that it is connected, not in use by another app, "
                "and allowed by Windows camera privacy settings."
            )
        with capture_lock:
            active_camera_capture = cap
        if stop_event.is_set():
            return

        frame = None
        for _ in range(5):
            captured, candidate = cap.read()
            if captured:
                frame = candidate
                break
            if stop_event.wait(0.2):
                return
        if frame is None:
            raise RuntimeError("The camera opened but did not provide a video frame.")
        if stop_event.is_set():
            return

        encoded, buffer = cv2.imencode(".jpg", frame)
        if not encoded:
            raise RuntimeError("The initial camera frame could not be encoded.")
        with frame_lock:
            latest_frame_jpeg = buffer.tobytes()

        with state_lock:
            if (
                attempt_id != camera_attempt_id
                or stop_event.is_set()
                or SYSTEM_STATE["camera_status"] != "Connecting"
            ):
                return
            SYSTEM_STATE["is_running"] = True
            SYSTEM_STATE["camera_status"] = "Active"
            SYSTEM_STATE["camera_error"] = None
            if camera_watchdog is not None:
                camera_watchdog.cancel()

        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                if stop_event.is_set():
                    break
                raise RuntimeError("The camera stopped returning frames.")

            face_res = detect_microexpression(frame)
            posture_res = detect_posture(frame)
            # There is no microphone capture in this app; do not invoke the audio module's demo simulator.
            audio_res = {"score": 0.0, "details": "no_audio_input"}
            fusion_result = fuse_signals(face_res, posture_res, audio_res)

            if fusion_result["is_distress"]:
                trigger_alert(fusion_result)
                with state_lock:
                    SYSTEM_STATE["last_alert"] = {
                        "time": time.time(),
                        "score": fusion_result["fusion_score"],
                        "details": fusion_result.get("details", {}),
                    }
                    SYSTEM_STATE["active_alerts_count"] += 1
                print(
                    f"[DISTRESS] Score: {fusion_result['fusion_score']:.2f} "
                    f"| {fusion_result['details']}"
                )

            details = face_res.get("details")
            if isinstance(details, dict) and "face_box" in details:
                fx, fy, fw, fh = details["face_box"]
                color = (0, 0, 255) if fusion_result["is_distress"] else (0, 255, 0)
                cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), color, 2)

            encoded, buffer = cv2.imencode(".jpg", frame)
            if not encoded:
                raise RuntimeError("Could not encode a camera frame for streaming.")
            with frame_lock:
                latest_frame_jpeg = buffer.tobytes()

            time.sleep(0.05)
    except Exception as exc:
        if not stop_event.is_set():
            error_message = f"Camera monitoring failed: {exc}"
            print(f"[ERROR] {error_message}")
    finally:
        if cap is not None:
            _release_camera(cap)
            with capture_lock:
                if active_camera_capture is cap:
                    active_camera_capture = None
        with state_lock:
            if attempt_id == camera_attempt_id:
                SYSTEM_STATE["is_running"] = False
                if error_message:
                    SYSTEM_STATE["camera_status"] = "Error"
                    SYSTEM_STATE["camera_error"] = error_message
                elif SYSTEM_STATE["camera_status"] == "Stopping":
                    SYSTEM_STATE["camera_status"] = "Idle"
                    SYSTEM_STATE["camera_error"] = None
                elif SYSTEM_STATE["camera_status"] == "Connecting":
                    SYSTEM_STATE["camera_status"] = "Error"
                    SYSTEM_STATE["camera_error"] = "Camera initialization ended before a frame was available."
                if camera_watchdog is not None:
                    camera_watchdog.cancel()
        print("[SYSTEM] Monitoring Thread Stopped.")


@app.post("/start")
def start_monitoring():
    global camera_attempt_id, camera_thread, camera_watchdog

    with start_lock:
        with state_lock:
            if SYSTEM_STATE["is_running"]:
                return {"status": "already_running", "camera_status": "Active"}
            if SYSTEM_STATE["camera_status"] == "Connecting":
                return {"status": "connecting", "camera_status": "Connecting"}
            if SYSTEM_STATE["camera_status"] == "Stopping":
                return {"status": "stopping", "camera_status": "Stopping"}
            if camera_thread is not None and camera_thread.is_alive():
                raise HTTPException(
                    status_code=503,
                    detail="A previous camera operation is still shutting down. Wait briefly and try again.",
                )
            if camera_watchdog is not None:
                camera_watchdog.cancel()
                camera_watchdog = None
            camera_attempt_id += 1
            attempt_id = camera_attempt_id
            SYSTEM_STATE["camera_status"] = "Connecting"
            SYSTEM_STATE["camera_error"] = None
            stop_event.clear()
            camera_thread = threading.Thread(
                target=monitoring_loop,
                args=(attempt_id,),
                name="camera-monitor",
                daemon=True,
            )
            camera_watchdog = threading.Timer(
                CAMERA_CONNECT_TIMEOUT_SECONDS,
                _camera_timeout,
                args=(
                    attempt_id,
                    "Connecting",
                    "Camera connection timed out. Check camera permissions, camera index, and whether another app is using it.",
                ),
            )
            camera_watchdog.daemon = True
            camera_watchdog.start()
            try:
                camera_thread.start()
            except Exception as exc:
                camera_watchdog.cancel()
                message = f"Could not start camera monitoring: {exc}"
                _set_camera_error(attempt_id, message)
                raise HTTPException(status_code=503, detail=message) from exc
            return {"status": "connecting", "camera_status": "Connecting"}


@app.post("/stop")
def stop_monitoring():
    global camera_watchdog
    with start_lock:
        with state_lock:
            worker_alive = camera_thread is not None and camera_thread.is_alive()
            if SYSTEM_STATE["camera_status"] not in ("Connecting", "Active", "Error") and not worker_alive:
                return {"status": "already_stopped", "camera_status": SYSTEM_STATE["camera_status"]}
            SYSTEM_STATE["camera_status"] = "Stopping"
            attempt_id = camera_attempt_id
            if camera_watchdog is not None:
                camera_watchdog.cancel()
            stop_event.set()
        camera_watchdog = threading.Timer(
            CAMERA_STOP_TIMEOUT_SECONDS,
            _camera_timeout,
            args=(
                attempt_id,
                "Stopping",
                "Camera shutdown timed out. The capture device may still be busy; wait before retrying.",
            ),
        )
        camera_watchdog.daemon = True
        camera_watchdog.start()
        with capture_lock:
            capture = active_camera_capture
        if capture is not None:
            threading.Thread(
                target=_release_camera,
                args=(capture,),
                name="camera-release",
                daemon=True,
            ).start()
    return {"status": "stopping_initiated", "camera_status": "Stopping"}


@app.get("/status")
def get_status():
    with state_lock:
        return dict(SYSTEM_STATE)

from config.firebase_config import db

@app.get("/alerts")
def get_alerts():
    """Fetch recent alerts. Useful if Frontend cannot connect to Firestore directly (Mock Mode)."""
    try:
        # Sort by timestamp desc
        docs = db.collection("alerts").stream()
        alerts_list = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            alerts_list.append(data)
        
        # Sort client-side mostly for mock; Firestore stream order depends on query
        alerts_list.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return alerts_list
    except Exception as e:
        print(f"Error fetching alerts: {e}")
        return []

# MJPEG Streaming Logic
from fastapi.responses import StreamingResponse
import io

def gen_frames():
    """Video streaming generator function."""
    while True:
        with state_lock:
            if not SYSTEM_STATE["is_running"]:
                break
        with frame_lock:
            if latest_frame_jpeg:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + latest_frame_jpeg + b'\r\n')
        time.sleep(0.05) # Cap at ~20 FPS for stream

@app.get("/video_feed")
def video_feed():
    """Returns MJPEG stream."""
    with state_lock:
        if not SYSTEM_STATE["is_running"] or latest_frame_jpeg is None:
            raise HTTPException(status_code=503, detail="Camera stream is not running.")
    return StreamingResponse(gen_frames(), media_type='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
