import unittest

from ai.incident_intelligence import analyze_incident, assess_incident


class IncidentAssessmentTests(unittest.TestCase):
    def test_missing_signals_are_uncertain_and_safe(self):
        assessment = assess_incident(timestamp=0)

        self.assertEqual(assessment["category"], "Uncertain / requires human review")
        self.assertEqual(assessment["severity"], "LOW")
        self.assertEqual(assessment["timestamp"], "1970-01-01T00:00:00+00:00")
        self.assertTrue(assessment["human_review_required"])
        self.assertFalse(assessment["automatic_response"])
        self.assertNotIn("confidence", assessment)

    def test_impact_signal_requires_human_review(self):
        assessment = assess_incident(
            face_result={"impact_detected": True},
            fusion_result={"is_distress": True, "fusion_score": 1.0},
            timestamp="2026-01-02T03:04:05Z",
        )

        self.assertEqual(assessment["category"], "Possible physical distress")
        self.assertEqual(assessment["severity"], "HIGH")
        self.assertEqual(assessment["detector_score"], 1.0)
        self.assertNotIn("confidence", assessment)
        self.assertIn("verify", assessment["recommended_response"])
        self.assertFalse(assessment["automatic_response"])

    def test_posture_motion_proxy_is_not_reported_as_confirmed_fall(self):
        assessment = assess_incident(posture_result={"score": 0.8})

        self.assertEqual(assessment["category"], "Fall or abnormal posture")
        self.assertEqual(assessment["severity"], "MEDIUM")
        self.assertIn("does not identify a fall", assessment["explanation"])

    def test_emotion_only_signal_is_not_an_emergency(self):
        assessment = assess_incident(face_result={"score": 0.9})

        self.assertEqual(assessment["category"], "Possible emotional distress")
        self.assertEqual(assessment["severity"], "LOW")
        self.assertIn("alone is not evidence of an emergency", assessment["explanation"])
        self.assertIn("Do not initiate an emergency response", assessment["recommended_response"])

    def test_audio_signal_and_simulated_output(self):
        measured = assess_incident(audio_result={"score": 0.95, "details": {"rms": 0.2}})
        simulated = assess_incident(
            audio_result={"score": 0.95, "details": "simulated_noise"}
        )

        self.assertEqual(measured["category"], "Audio distress")
        self.assertEqual(measured["severity"], "HIGH")
        self.assertEqual(simulated["category"], "Uncertain / requires human review")
        self.assertIn("was marked as simulated", simulated["explanation"])

    def test_only_explicit_model_confidence_is_returned(self):
        with_confidence = assess_incident(
            fusion_result={"fusion_score": 0.72, "confidence": 0.61}
        )
        without_confidence = assess_incident(fusion_result={"fusion_score": 0.72})

        self.assertEqual(with_confidence["confidence"], 0.61)
        self.assertEqual(with_confidence["detector_score"], 0.72)
        self.assertNotIn("confidence", without_confidence)

    def test_saved_incident_shape_is_adapted(self):
        assessment = analyze_incident(
            {
                "timestamp": 123,
                "confidence_score": 0.9,
                "details": {
                    "trigger": "IMPACT_DETECTED",
                    "face": {"score": 0.4},
                    "posture": {"score": 0.2},
                    "audio": {"score": 0.1},
                },
            }
        )

        self.assertEqual(assessment["category"], "Possible physical distress")
        self.assertEqual(assessment["timestamp"], "1970-01-01T00:02:03+00:00")
        self.assertEqual(assessment["detector_score"], 0.9)
        self.assertNotIn("confidence", assessment)

    def test_existing_fusion_output_supplies_nested_sensor_results(self):
        assessment = assess_incident(
            fusion_result={
                "is_distress": True,
                "fusion_score": 1.0,
                "details": {
                    "face": {"score": 0.4, "impact_detected": True},
                    "posture": {"score": 0.9},
                    "audio": {"score": 0.1},
                    "trigger": "IMPACT_DETECTED",
                },
            }
        )

        self.assertEqual(assessment["category"], "Possible physical distress")
        self.assertEqual(assessment["severity"], "CRITICAL")


if __name__ == "__main__":
    unittest.main()
