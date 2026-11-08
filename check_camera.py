"""Save a test picture from every camera so you can compare them.

Run:  python check_camera.py
Pictures are saved in the camera_check/ folder.
"""
import os
import time

import cv2

from cam_detection.camera import open_camera

os.makedirs("camera_check", exist_ok=True)
for index in range(4):
    cap = open_camera(index)
    if not cap.isOpened():
        continue
    for label, size in [("default", None), ("1280x720", (1280, 720)), ("1920x1080", (1920, 1080))]:
        if size:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        for _ in range(20):  # let the camera warm up / adjust exposure
            cap.read()
            time.sleep(0.03)
        ok, frame = cap.read()
        if not ok:
            print(f"camera {index} [{label}]: could not read a frame")
            continue
        h, w = frame.shape[:2]
        path = f"camera_check/cam{index}_{label}.jpg"
        cv2.imwrite(path, frame)
        print(f"camera {index} [{label}]: actual {w}x{h} -> {path}")
    cap.release()
print("Done.")
