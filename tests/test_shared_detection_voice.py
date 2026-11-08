import threading
import unittest
from collections import deque
from types import SimpleNamespace

from web_app import create_app


class FakeWorker:
    def __init__(self):
        self.new_frame = threading.Condition()
        self.stats = {"fps": 0, "total": 0, "counts": [], "error": None,
                      "camera": 0, "resolution": ""}
        self.events = deque()
        self.detector = SimpleNamespace(labels={"person", "car", "dog"})
        self.alerter = SimpleNamespace(labels={"person"})
        self.voice = SimpleNamespace(labels={"car"}, available=True)
        self.settings = {"camera": 0, "lang": "en", "conf": 0.5, "text_size": 1.0,
                         "alerts": True, "voice": True, "clip": True}

    def get_settings(self):
        return dict(self.settings)

    def update(self, **changes):
        self.settings.update(changes)
        return dict(self.settings)


class SharedDetectionVoiceTests(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()
        self.client = create_app(self.worker).test_client()

    def test_stats_exposes_one_combined_selection(self):
        response = self.client.get("/api/stats")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["detection_labels"], ["car", "person"])

    def test_page_has_one_picker_and_inline_voice_toggle(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        response.close()

        self.assertIn('id="detectionAdd"', html)
        self.assertIn('class="voice-inline" id="voiceBlock"', html)
        self.assertIn('id="swVoice"', html)
        self.assertNotIn('id="tgAdd"', html)
        self.assertNotIn('id="voiceAdd"', html)

    def test_shared_selection_updates_alert_and_voice_labels(self):
        response = self.client.post(
            "/api/settings",
            json={"detection_labels": ["dog", "person", "not-a-model-label"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.worker.alerter.labels, {"dog", "person"})
        self.assertEqual(self.worker.voice.labels, {"dog", "person"})

    def test_legacy_alert_selection_also_updates_voice(self):
        response = self.client.post("/api/settings", json={"alert_labels": ["car"]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.worker.alerter.labels, {"car"})
        self.assertEqual(self.worker.voice.labels, {"car"})


if __name__ == "__main__":
    unittest.main()
