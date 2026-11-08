"""Cross-platform OpenCV camera opening helpers."""
import sys

import cv2


def camera_backends(platform: str | None = None) -> tuple[int, ...]:
    """Return camera backends in the order they should be tried."""
    platform = platform or sys.platform
    if platform == "win32":
        # Media Foundation is the modern Windows backend. DirectShow is a useful
        # fallback for older USB cameras and drivers.
        return cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY
    return (cv2.CAP_ANY,)


def open_camera(source):
    """Open a camera index reliably, while leaving URLs/files on auto-detection."""
    if not isinstance(source, int):
        return cv2.VideoCapture(source)

    capture = None
    for backend in camera_backends():
        capture = cv2.VideoCapture(source, backend)
        if capture.isOpened():
            return capture
        capture.release()
    return capture
