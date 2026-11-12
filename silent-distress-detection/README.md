# ResQPay AI

A privacy-first, edge-AI system to detect silent distress signals (micro-expressions, posture, audio) and alert personnel via a real-time dashboard.

## 🚀 Features

- **Multimodal AI**: Combines facial motion (OpenCV), posture motion heuristics, and simulated audio stress.
- **Privacy First**: No video recording. No face recognition/identity storage. Only temporal alert metadata is saved.
- **Real-Time Dashboard**: React-based UI to monitor system status and view alerts.
- **Human-in-the-Loop**: Staff verify or dismiss alerts; explainable incident summaries support, but do not replace, human decisions.
- **Edge Processing**: All AI processing runs locally on the backend.

## 🛠 Tech Stack

- **Backend**: Python, FastAPI, OpenCV, NumPy, Firebase Admin
- **Frontend**: React (Create React App), CSS3
- **Database/Notification**: Google Firebase (Firestore, Cloud Messaging)

## 📂 Project Structure

```
silent-distress-detection/
├── backend/            # Python FastAPI Server + AI Logic
│   ├── ai/             # Computer Vision & Audio Modules
│   ├── alerts/         # Alert Logic & Firebase Connector
│   └── app.py          # Main Entry Point
├── frontend/           # React Web Application
│   ├── src/pages/      # Dashboard, Alerts, Settings
│   └── src/services/   # API & Firebase Services
└── firebase/           # Firestore Rules
```

## ⚡ Quick Start

### 1. Backend Setup

1. Navigate to backend: `cd backend`
2. Create virtual environment: `py -3.13 -m venv venv`
3. Activate venv:
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Run the server: `python app.py` (or `uvicorn app:app --reload`)

The webcam must be connected to the machine running this backend. On Windows,
monitoring uses DirectShow; set backend `RESQPAY_CAMERA_INDEX` (default `0`) if
the camera is exposed at a different device index. Allow desktop apps to access
the camera in Windows Privacy & security settings, and close other apps that may
be holding the camera. The dashboard reports a connection timeout or camera error
instead of claiming the camera is active without receiving a frame.

**Note on Firebase**: By default, the system runs in **Mock Mode** (alerts stored in memory) if no `serviceAccountKey.json` is found. To connect real Firebase:
- Place your `serviceAccountKey.json` on your machine.
- Set backend `FIREBASE_CREDENTIALS` in `.env` to the service-account path (relative to `backend/`).

### 2. Frontend Setup

1. Navigate to frontend: `cd frontend`
2. Install dependencies: `npm install`
3. Start dev server: `npm start`
4. Open browser at `http://localhost:3000`

Copy `frontend/.env.example` to `frontend/.env` and set the Firebase Web App
configuration values from Firebase Console > Project settings. In Firebase
Console, enable **Authentication > Sign-in method > Email/Password** and create
staff/admin users under **Authentication > Users**. The app does not create
accounts from the sign-in form. The email must match an existing Firebase Auth
user, and the password must be that account's Firebase password. Restart
`npm start` after editing `frontend/.env`.

The backend must use credentials for the same Firebase project to verify the
frontend ID tokens. Copy the root `.env.example` to `backend/.env`, set
`FIREBASE_CREDENTIALS` to a locally stored service-account JSON file (do not
commit it), and set `RESQPAY_ADMIN_EMAILS` to authorized administrator
addresses. The camera requires no Firebase account: the backend uses the webcam
connected to the machine running FastAPI.

Local development on `localhost` uses `http://localhost:8000` by default. Set
`REACT_APP_API_URL` in `frontend/.env` only to override it. Never put the Firebase
Admin service account or PayPal secret in the frontend.

## 🛡 Privacy & Ethics

- **No Surveillance**: This is NOT a surveillance system. It does not record video.
- **No Identity**: It detects *emotions* and *distress*, not *people*. It cannot tell "Who" is in distress, only "That" someone is.
- **Ephemeral Processing**: Video frames are processed in RAM and discarded immediately.

## 📸 Usage

1. Go to the **Dashboard** page.
2. Click **Start Monitoring**.
3. If using a webcam, simulate distress (e.g., frowning, hands up, freezing).
4. Sign in on the **Emergency incidents** page to review detector alerts and verify or dismiss them.
5. Submit a relief campaign, obtain administrator approval, then use the **Donations** page to complete a Sandbox donation and review its transaction.

---
*Created for AI Safety Hackathon*

## ResQPay AI MVP

The existing `/start`, `/stop`, `/status`, `/alerts`, and `/video_feed` endpoints
remain in place. Detection continues to run through the existing face, posture,
audio, fusion, and alert modules. The new FastAPI router adds:

- `GET /api/incidents` and `GET /api/incidents/{id}`: authenticated incident details
  with explainable triage summaries derived from the existing detector output.
- `POST /api/incidents/assess`: authenticated, non-persisting rule-based assessment
  accepting available `face_result`, `posture_result`, `audio_result`, and
  `fusion_result` values. It reports category, severity, explanation, recommended
  response, and timestamp; confidence is included only when a model explicitly
  supplies it.
- `PATCH /api/incidents/{id}/verification`: staff verification (`confirmed` or
  `dismissed`, or `resolved`) recorded on the existing Firestore `alerts` document.
- `GET /api/campaigns`, `GET /api/campaigns/{id}`, `POST /api/campaigns`,
  `POST /api/campaigns/{id}/submit`, `GET /api/admin/campaigns`, and
  `PATCH /api/campaigns/{id}/approval`: verified-incident campaigns with
  DRAFT → PENDING_APPROVAL → APPROVED/REJECTED review, progress, and completion.
  Campaign creation is administrator-only and requires a `confirmed` incident.
  Public listings include approved or completed campaigns; donation orders require
  APPROVED status and cannot exceed the recorded remaining target.
- `POST /api/donations/create-order`, `POST /api/donations/capture`, and
  `GET /api/transactions`: PayPal Sandbox donations and per-user history.

Configure backend-only `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` for Sandbox
checkout, `RESQPAY_ADMIN_EMAILS` as a comma-separated list of administrator emails
(or assign Firebase Admin custom claim `admin: true`), and optionally
`RESQPAY_FRONTEND_URL`. Staff verification, campaign submission, and donations
require Firebase sign-in. Campaign approval is administrator-only. Firebase Admin
uses the existing backend configuration; without valid Firebase credentials it
falls back to in-memory mock storage, which is not persistent.

PayPal donations use only the Orders API Sandbox host configured by
`PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com`. The backend stores pending
orders/transactions before redirecting, validates PayPal's order, campaign,
capture amount, and currency on return, and only updates campaign funding after
PayPal confirms a completed capture. Network-ambiguous captures remain pending
and can be retried with PayPal's request idempotency key; cancelled and explicitly
failed payments are not counted as raised funds.
