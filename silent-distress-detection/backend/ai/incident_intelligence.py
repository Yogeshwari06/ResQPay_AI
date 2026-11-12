"""Transparent, rule-based triage of existing distress detector outputs.

These assessments are decision support only. They do not verify an emergency,
create alerts, contact responders, or start fundraising.
"""

from datetime import datetime, timezone
import math
from typing import Any, Optional


_POSTURE_THRESHOLD = 0.7
_AUDIO_THRESHOLD = 0.7
_FACE_THRESHOLD = 0.5


def _valid_score(result: Any) -> Optional[float]:
    if not isinstance(result, dict):
        return None
    value = result.get("score", result.get("distress_score"))
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        return None
    return score


def _timestamp(value: Any) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and math.isfinite(value):
        try:
            parsed = datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise ValueError("timestamp is outside the supported range") from error
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("timestamp must be an epoch value or ISO-8601 string") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def assess_incident(
    face_result: Optional[dict] = None,
    posture_result: Optional[dict] = None,
    audio_result: Optional[dict] = None,
    fusion_result: Optional[dict] = None,
    timestamp: Any = None,
) -> dict:
    """Assess any available face, posture, audio, and fusion outputs.

    Thresholds are triage heuristics, not probabilities. Only an explicit
    ``confidence`` value from the fusion output is exposed as confidence.
    """
    face_result = face_result if isinstance(face_result, dict) else {}
    posture_result = posture_result if isinstance(posture_result, dict) else {}
    audio_result = audio_result if isinstance(audio_result, dict) else {}
    fusion_result = fusion_result if isinstance(fusion_result, dict) else {}

    fused_details = fusion_result.get("details")
    if isinstance(fused_details, dict):
        if not face_result:
            nested_face = fused_details.get("face")
            face_result = nested_face if isinstance(nested_face, dict) else {}
        if not posture_result:
            nested_posture = fused_details.get("posture")
            posture_result = nested_posture if isinstance(nested_posture, dict) else {}
        if not audio_result:
            nested_audio = fused_details.get("audio")
            audio_result = nested_audio if isinstance(nested_audio, dict) else {}
        if fused_details.get("trigger") == "IMPACT_DETECTED":
            face_result = {**face_result, "impact_detected": True}

    face_score = _valid_score(face_result)
    posture_score = _valid_score(posture_result)
    audio_score = _valid_score(audio_result)

    audio_detail = audio_result.get("details")
    audio_is_simulated = (
        isinstance(audio_detail, str)
        and audio_detail in ("simulated_noise", "no_audio_input")
    )
    if audio_is_simulated:
        audio_score = None

    impact_detected = face_result.get("impact_detected") is True
    posture_anomaly = posture_score is not None and posture_score >= _POSTURE_THRESHOLD
    audio_distress = audio_score is not None and audio_score >= _AUDIO_THRESHOLD
    possible_emotional_distress = face_score is not None and face_score >= _FACE_THRESHOLD
    fusion_score = _valid_score(fusion_result) if "score" in fusion_result else None
    if fusion_score is None:
        fusion_value = fusion_result.get(
            "fusion_score", fusion_result.get("confidence_score")
        )
        try:
            fusion_score = float(fusion_value)
        except (TypeError, ValueError):
            fusion_score = None
        if (
            fusion_score is not None
            and (not math.isfinite(fusion_score) or not 0.0 <= fusion_score <= 1.0)
        ):
            fusion_score = None

    if impact_detected:
        category = "Possible physical distress"
        severity = "HIGH"
        explanation = (
            "The face-motion detector reported a possible physical impact. "
            "This heuristic can produce false positives and requires human verification."
        )
        corroborated = posture_anomaly or audio_distress
        if (
            corroborated
            and fusion_result.get("is_distress") is True
            and fusion_score is not None
            and fusion_score >= 0.85
        ):
            severity = "CRITICAL"
            explanation += (
                " A separate sensor also reported an anomaly and fusion crossed its "
                "distress threshold; this remains an unverified detector result."
            )
        recommendation = (
            "Have a staff member promptly check the reported location and verify "
            "whether assistance is needed. Do not dispatch automatically."
        )
    elif posture_anomaly:
        category = "Fall or abnormal posture"
        severity = "HIGH" if posture_score >= 0.9 else "MEDIUM"
        explanation = (
            f"The posture module reported a motion-proxy score of {posture_score:.2f}. "
            "It uses motion heuristics and does not identify a fall or body pose."
        )
        recommendation = (
            "Ask staff to review the scene and verify the person's condition; "
            "the posture score alone does not confirm a fall."
        )
    elif audio_distress:
        category = "Audio distress"
        severity = "HIGH" if audio_score >= 0.9 else "MEDIUM"
        explanation = (
            f"The audio module reported a distress-like score of {audio_score:.2f}. "
            "The score is an acoustic heuristic, not a confirmed distress event."
        )
        recommendation = (
            "Have staff review available context and verify whether assistance is needed."
        )
    elif possible_emotional_distress:
        category = "Possible emotional distress"
        severity = "LOW"
        explanation = (
            f"The face module reported an expression-proxy score of {face_score:.2f}. "
            "Emotion or facial appearance alone is not evidence of an emergency."
        )
        recommendation = (
            "Do not initiate an emergency response from this signal alone; seek "
            "independent context and human review."
        )
    elif (
        fusion_result.get("is_distress") is True
        or (fusion_score is not None and fusion_score >= 0.85)
    ):
        category = "Uncertain / requires human review"
        severity = "MEDIUM"
        explanation = (
            "The fusion output indicates a possible distress signal, but available "
            "sensor results do not support a more specific category."
        )
        recommendation = (
            "Have a staff member review the available context before deciding whether "
            "any response is appropriate."
        )
    else:
        category = "Uncertain / requires human review"
        severity = "LOW"
        explanation = (
            "Available sensor outputs are missing, inconclusive, or below the "
            "rule-based triage thresholds."
        )
        recommendation = (
            "No automated action is recommended. Obtain more context or have staff "
            "review if there is an independent concern."
        )

    assessment = {
        "category": category,
        "severity": severity,
        "explanation": explanation,
        "recommended_response": recommendation,
        "timestamp": _timestamp(timestamp),
        "human_review_required": True,
        "automatic_response": False,
    }

    # FusionEngine emits a fusion_score, not a calibrated confidence. Keep it
    # explicitly labeled as a raw detector score rather than a probability.
    if fusion_score is not None:
        assessment["detector_score"] = fusion_score
    explicit_confidence = _valid_score({"score": fusion_result.get("confidence")})
    if explicit_confidence is not None:
        assessment["confidence"] = explicit_confidence

    if audio_is_simulated:
        assessment["explanation"] += (
            " The audio result was marked as simulated or no-input and was excluded."
        )
    return assessment


def analyze_incident(incident: dict) -> dict:
    """Assess an existing Firestore alert using its saved detector outputs."""
    incident = incident if isinstance(incident, dict) else {}
    details = incident.get("details")
    details = details if isinstance(details, dict) else {}
    face_result = details.get("face")
    posture_result = details.get("posture")
    audio_result = details.get("audio")
    fusion_result = details.get("fusion")

    if not isinstance(fusion_result, dict):
        fusion_result = {}
    if "fusion_score" not in fusion_result:
        score = incident.get("fusion_score", incident.get("confidence_score"))
        if score is not None:
            fusion_result["fusion_score"] = score
    if details.get("trigger") == "IMPACT_DETECTED":
        if not isinstance(face_result, dict):
            face_result = {}
        face_result = {**face_result, "impact_detected": True}

    return assess_incident(
        face_result=face_result,
        posture_result=posture_result,
        audio_result=audio_result,
        fusion_result=fusion_result,
        timestamp=incident.get("timestamp"),
    )
