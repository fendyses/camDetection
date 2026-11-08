"""Open a camera, detect objects live, and show them on screen.

Usage:
    python main.py                 # default webcam (index 0)
    python main.py --camera 1      # another camera
    python main.py --source rtsp://user:pass@ip/stream   # IP camera / video file
    python main.py --conf 0.4 --model yolo11s.pt

Keys: q / Esc = quit, s = save snapshot
"""
import argparse
import time
from collections import Counter
from datetime import datetime

import cv2

from cam_detection.detector import ObjectDetector, draw_detections
from cam_detection.telegram_alert import TelegramAlerter, parse_labels
from cam_detection.voice import VoiceAnnouncer
from cam_detection.translations import translate, ui


def parse_args():
    p = argparse.ArgumentParser(description="Live camera object detection")
    p.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    p.add_argument("--source", help="video URL or file path (overrides --camera)")
    p.add_argument("--model", default="yolo11n.pt", help="YOLO model (n=fast, s/m/l/x=more accurate)")
    p.add_argument("--conf", type=float, default=0.5, help="minimum confidence 0-1")
    p.add_argument("--device", default=None, help="'mps' (Apple GPU), 'cpu', or 'cuda'")
    p.add_argument("--lang", choices=["en", "ms"], default="en", help="label language: en = English (default), ms = Malay")
    p.add_argument("--text-size", type=float, default=1.0, help="label size multiplier, e.g. 1.5 = bigger")
    p.add_argument("--alert", help="send a Telegram alert for these objects, e.g. \"teddy bear,cow\"")
    p.add_argument("--alert-cooldown", type=float, default=60,
                   help="seconds to wait before alerting again for the same object (default 60)")
    p.add_argument("--clip-seconds", type=float, default=5,
                   help="length of the video clip sent with each alert (0 = photo only)")
    p.add_argument("--voice", help="speak out loud for these objects, e.g. \"teddy bear\"")
    p.add_argument("--voice-cooldown", type=float, default=10,
                   help="seconds before speaking again for the same object (default 10)")
    p.add_argument("--width", type=int, default=1280, help="requested camera width (default 1280)")
    p.add_argument("--height", type=int, default=720, help="requested camera height (default 720)")
    return p.parse_args()


def main():
    args = parse_args()
    source = args.source if args.source else args.camera

    print(f"Loading model {args.model} ...")
    detector = ObjectDetector(args.model, args.conf, args.device)
    print(f"Model knows {len(detector.labels)} objects")

    alerter = None
    if args.alert:
        alerter = TelegramAlerter(parse_labels(args.alert, "--alert", detector.labels),
                                  args.alert_cooldown, args.lang, clip_seconds=args.clip_seconds)
        print(f"Telegram alerts on for: {', '.join(sorted(alerter.labels))}")
    voice = None
    if args.voice:
        voice = VoiceAnnouncer(parse_labels(args.voice, "--voice", detector.labels),
                               args.voice_cooldown, args.lang)
        print(f"Voice on for: {', '.join(sorted(voice.labels))}")

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(
            f"Could not open camera/source: {source}\n"
            "On macOS, allow camera access for your terminal in "
            "System Settings > Privacy & Security > Camera."
        )

    if args.width and args.height:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera {source} opened at {w}x{h}")

    # Resizable window that scales the whole frame to fit (avoids a cropped/"zoomed" look).
    cv2.namedWindow("Camera Object Detection", cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow("Camera Object Detection", 1024, int(1024 * h / max(w, 1)))

    print("Running. Press 'q' to quit, 's' to save a snapshot.")
    last_summary, prev_time = "", time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            print("Stream ended or camera disconnected.")
            break

        detections = detector.detect(frame)

        now = time.time()
        fps = 1 / max(now - prev_time, 1e-6)
        prev_time = now
        draw_detections(frame, detections, fps=fps, text_scale=args.text_size, lang=args.lang,
                        highlight=(alerter.labels if alerter else set()) | (voice.labels if voice else set()))
        if voice:
            voice.check(detections)
        if alerter:
            ok_jpg, buf = cv2.imencode(".jpg", frame)
            if ok_jpg:
                alerter.check(detections, buf.tobytes(), camera=source)

        counts = Counter(translate(d.label, args.lang) for d in detections)
        summary = ", ".join(f"{n} x {label}" for label, n in counts.most_common())
        if summary != last_summary:
            print(f"[{datetime.now():%H:%M:%S}] {summary or ui('nothing', args.lang)}")
            last_summary = summary

        cv2.imshow("Camera Object Detection", frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == ord("s"):
            name = f"snapshot_{datetime.now():%Y%m%d_%H%M%S}.jpg"
            cv2.imwrite(name, frame)
            print(f"Saved {name}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
