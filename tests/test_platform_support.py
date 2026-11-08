import unittest
from unittest.mock import MagicMock, call, patch

import cv2

from cam_detection.camera import camera_backends, open_camera
from cam_detection.voice import VoiceAnnouncer


class CameraBackendTests(unittest.TestCase):
    def test_windows_tries_native_backends_then_auto(self):
        self.assertEqual(
            camera_backends("win32"),
            (cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY),
        )

    def test_non_windows_uses_auto_backend(self):
        self.assertEqual(camera_backends("darwin"), (cv2.CAP_ANY,))
        self.assertEqual(camera_backends("linux"), (cv2.CAP_ANY,))

    @patch("cam_detection.camera.sys.platform", "win32")
    @patch("cam_detection.camera.cv2.VideoCapture")
    def test_windows_falls_back_when_first_backend_fails(self, video_capture):
        msmf = MagicMock()
        msmf.isOpened.return_value = False
        dshow = MagicMock()
        dshow.isOpened.return_value = True
        video_capture.side_effect = [msmf, dshow]

        self.assertIs(open_camera(0), dshow)
        self.assertEqual(
            video_capture.call_args_list,
            [call(0, cv2.CAP_MSMF), call(0, cv2.CAP_DSHOW)],
        )
        msmf.release.assert_called_once_with()


class VoiceTests(unittest.TestCase):
    @patch("cam_detection.voice.subprocess.Popen")
    @patch("cam_detection.voice.shutil.which", return_value=r"C:\Windows\System32\powershell.exe")
    @patch("cam_detection.voice.sys.platform", "win32")
    def test_windows_uses_powershell_speech(self, _which, popen):
        announcer = VoiceAnnouncer({"person"})
        announcer.say("Alert! Person detected.")

        command = popen.call_args.args[0]
        self.assertEqual(command[0], r"C:\Windows\System32\powershell.exe")
        self.assertIn("System.Speech", command[-3])
        self.assertEqual(command[-2:], ["en-US", "Alert! Person detected."])

    @patch("cam_detection.voice.subprocess.Popen")
    @patch("cam_detection.voice.shutil.which", return_value="/usr/bin/say")
    @patch("cam_detection.voice.sys.platform", "darwin")
    def test_macos_keeps_say_voice(self, _which, popen):
        announcer = VoiceAnnouncer({"person"}, lang="en")
        announcer.say("Alert! Person detected.")

        self.assertEqual(
            popen.call_args.args[0],
            ["/usr/bin/say", "-v", "Samantha", "Alert! Person detected."],
        )

    @patch("cam_detection.voice.shutil.which", return_value=None)
    @patch("cam_detection.voice.sys.platform", "linux")
    def test_unsupported_platform_disables_voice(self, _which):
        self.assertFalse(VoiceAnnouncer(set()).available)


if __name__ == "__main__":
    unittest.main()
