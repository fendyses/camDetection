import sys
import unittest
from unittest import mock

import web_app
from cam_detection.road import RoadSettings


class RoadSettingsWiringTests(unittest.TestCase):
    def test_command_line_defaults_reach_road_checker_unchanged(self):
        """The app must hand every road setting to the right field (regression: values shifted)."""
        captured = {}

        class Stop(Exception):
            pass

        def fake_checker(settings):
            captured["settings"] = settings
            raise Stop

        with mock.patch.object(sys, "argv", ["web_app.py", "--esp-port", "none", "--no-login"]), \
                mock.patch.object(web_app, "ObjectDetector"), \
                mock.patch.object(web_app.TelegramClient, "from_env", return_value=None), \
                mock.patch.object(web_app, "VoiceAnnouncer"), \
                mock.patch.object(web_app, "load_env", return_value={"FLASK_SECRET_KEY": "x"}), \
                mock.patch.object(web_app, "RoadChecker", side_effect=fake_checker):
            with self.assertRaises(Stop):
                web_app.main()
        self.assertEqual(captured["settings"], RoadSettings())


if __name__ == "__main__":
    unittest.main()
