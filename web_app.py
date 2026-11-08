"""Run object detection in the browser.

Usage:
    python web_app.py              # open http://localhost:8000 on this Mac
    python web_app.py --phone      # also allow phones/laptops on the same Wi-Fi
    python web_app.py --camera 1 --alert "teddy bear,cow" --voice "teddy bear"

The camera is read on this computer; the browser only shows the result.
"""
import argparse
import hmac
import secrets
import socket
import threading
import time
from collections import Counter, deque
from datetime import datetime
from pathlib import Path

import cv2
from flask import Flask, Response, abort, jsonify, redirect, request, send_from_directory, session

from cam_detection.detector import ObjectDetector, draw_detections
from cam_detection.telegram_alert import (TelegramAlerter, TelegramClient, load_env, parse_labels,
                                          save_env_value)
from cam_detection.telegram_bot import TelegramBot
from cam_detection.voice import VoiceAnnouncer
from cam_detection.translations import translate, ui

WEB_DIR = Path(__file__).parent / "web"
MAX_CAMERAS = 6          # camera numbers 0..5 are checked when scanning
THUMB_WIDTH = 320        # preview picture width in the camera picker
DARK_LEVEL = 12          # average brightness below this = "camera looks black"


def make_thumb(frame) -> bytes:
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (THUMB_WIDTH, int(THUMB_WIDTH * h / w)))
    return cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()


class CameraWorker:
    """Reads the camera and runs detection in a background thread."""

    def __init__(self, detector: ObjectDetector, camera: int, width: int, height: int,
                 lang: str, text_size: float, alerter: TelegramAlerter | None = None,
                 voice: VoiceAnnouncer | None = None, alerts_on: bool = False,
                 voice_on: bool = False, clip_seconds: float = 5):
        self.detector = detector
        self.alerter = alerter
        self.voice = voice
        self.clip_seconds = clip_seconds
        self.width, self.height = width, height
        self.lock = threading.Lock()
        self.new_frame = threading.Condition()
        self.settings = {"camera": camera, "lang": lang, "conf": detector.confidence,
                         "text_size": text_size, "alerts": alerts_on and alerter is not None,
                         "voice": voice_on and voice is not None, "clip": clip_seconds > 0}
        self.jpeg: bytes | None = None
        self.frame_id = 0
        self.stats: dict = {"fps": 0, "total": 0, "counts": [], "error": None,
                            "camera": camera, "resolution": ""}
        self.events: deque = deque(maxlen=15)
        self.cameras: list[dict] = []        # [{"index": 0, "dark": False}, ...]
        self.thumbs: dict[int, bytes] = {}
        self.scanning = True                  # scan once at start-up
        self._cap = None
        self._opened = None
        threading.Thread(target=self._loop, daemon=True).start()

    def update(self, **changes):
        with self.lock:
            self.settings.update(changes)
            return dict(self.settings)

    def get_settings(self):
        with self.lock:
            return dict(self.settings)

    def _open(self, index: int) -> bool:
        if self._cap is not None:
            self._cap.release()
        self._cap = cv2.VideoCapture(index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._opened = index
        return self._cap.isOpened()

    def request_scan(self):
        self.scanning = True

    def _scan(self):
        """Find which camera numbers work and take a preview picture from each."""
        if self._cap is not None:
            self._cap.release()
            self._cap, self._opened = None, None
        found, thumbs, misses = [], {}, 0
        for index in range(MAX_CAMERAS):
            cap = cv2.VideoCapture(index)
            if not cap.isOpened():
                cap.release()
                misses += 1
                if misses >= 2:
                    break
                continue
            misses = 0
            frame = None
            for _ in range(12):  # let exposure settle
                ok, f = cap.read()
                if ok:
                    frame = f
                time.sleep(0.03)
            cap.release()
            if frame is None:
                continue
            found.append({"index": index, "dark": bool(frame.mean() < DARK_LEVEL)})
            thumbs[index] = make_thumb(frame)
        self.cameras, self.thumbs = found, thumbs
        print("Cameras found: " + (", ".join(
            f"{c['index']}{' (black picture)' if c['dark'] else ''}" for c in found) or "none"))
        self.scanning = False

    def _set_error(self, message: str):
        with self.new_frame:
            self.stats = {**self.stats, "error": message}

    def _loop(self):
        state = {"prev": time.time(), "fps": 0.0, "last_summary": None}
        while True:
            try:
                self._step(state)
            except Exception as exc:  # keep the stream alive whatever happens
                print(f"Camera loop error: {exc!r}")
                self._set_error(f"Error: {exc}")
                time.sleep(1)

    def _step(self, state: dict):
        """Read one frame, detect objects and publish the result."""
        if self.scanning:
            self._scan()
        s = self.get_settings()
        if s["camera"] != self._opened:
            if not self._open(s["camera"]):
                self._opened = None  # retry later
                self._set_error(f"Camera {s['camera']} could not be opened")
                time.sleep(2)
                return

        ok, frame = self._cap.read()
        if not ok:
            self._set_error("No image from the camera")
            time.sleep(0.5)
            return

        if self.frame_id % 60 == 0:  # keep the live camera's preview fresh
            self.thumbs[s["camera"]] = make_thumb(frame)
            for cam in self.cameras:
                if cam["index"] == s["camera"]:
                    cam["dark"] = bool(frame.mean() < DARK_LEVEL)

        self.detector.confidence = s["conf"]
        detections = self.detector.detect(frame)

        now = time.time()
        instant = 1 / max(now - state['prev'], 1e-6)
        state['prev'] = now
        fps = instant if state['fps'] == 0 else state['fps'] * 0.9 + instant * 0.1  # smoothed
        state['fps'] = fps

        highlight = (self.alerter.labels if self.alerter else set()) | (self.voice.labels if self.voice else set())
        draw_detections(frame, detections, fps=fps, text_scale=s["text_size"], lang=s["lang"],
                        highlight=highlight)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return
        if self.voice:
            self.voice.lang = s["lang"]
            self.voice.enabled = s["voice"]
            self.voice.check(detections)
        if self.alerter:
            self.alerter.enabled = s["alerts"]
            self.alerter.clip_seconds = (self.clip_seconds or 5) if s["clip"] else 0
            self.alerter.lang = s["lang"]
            self.alerter.check(detections, buf.tobytes(), camera=s["camera"])

        counts = Counter(translate(d.label, s["lang"]) for d in detections).most_common()
        summary = ", ".join(f"{n} x {name}" for name, n in counts) or ui("nothing", s["lang"])
        if summary != state['last_summary']:
            self.events.appendleft({"time": datetime.now().strftime("%H:%M:%S"), "text": summary})
            state['last_summary'] = summary

        h, w = frame.shape[:2]
        with self.new_frame:
            self.jpeg = buf.tobytes()
            self.frame_id += 1
            self.stats = {"fps": round(fps, 1), "total": len(detections), "counts": counts,
                          "error": None, "camera": s["camera"], "resolution": f"{w}x{h}"}
            self.new_frame.notify_all()

    def frames(self):
        """Yield every new JPEG frame (for the MJPEG stream)."""
        last = -1
        while True:
            with self.new_frame:
                self.new_frame.wait_for(lambda: self.frame_id != last, timeout=2)
                if self.frame_id == last or self.jpeg is None:
                    continue
                last, jpeg = self.frame_id, self.jpeg
            yield jpeg


def create_app(worker: CameraWorker, login: tuple[str, str] | None = None,
               secret_key: str | None = None) -> Flask:
    app = Flask(__name__)
    app.secret_key = secret_key or secrets.token_hex(32)
    app.config.update(SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=7 * 24 * 3600)

    @app.before_request
    def require_login():
        if login is None or request.path in ("/login", "/favicon.ico") or session.get("user"):
            return None
        if request.path.startswith(("/api/", "/video", "/snapshot", "/camera/")):
            return jsonify({"error": "login required"}), 401
        return redirect("/login")

    @app.route("/login", methods=["GET", "POST"])
    def login_page():
        if login is None:
            return redirect("/")
        if request.method == "POST":
            user = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            ok_user = hmac.compare_digest(user.lower().encode(), login[0].lower().encode())
            ok_pass = hmac.compare_digest(password.encode(), login[1].encode())
            if ok_user and ok_pass:
                session.clear()
                session["user"] = login[0]
                session.permanent = True
                print(f"[Login] {login[0]} logged in from {request.remote_addr}")
                return redirect("/")
            print(f"[Login] failed attempt from {request.remote_addr}")
            time.sleep(1)  # slow down password guessing
            return redirect("/login?error=1")
        return send_from_directory(WEB_DIR, "login.html")

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect("/login")

    @app.get("/api/me")
    def me():
        return jsonify({"user": session.get("user"), "login": login is not None})

    @app.get("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/video")
    def video():
        def stream():
            for jpeg in worker.frames():
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
        return Response(stream(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.get("/snapshot.jpg")
    def snapshot():
        if worker.jpeg is None:
            abort(503)
        name = f"snapshot_{datetime.now():%Y%m%d_%H%M%S}.jpg"
        return Response(worker.jpeg, mimetype="image/jpeg",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/cameras")
    def cameras():
        return jsonify({"scanning": worker.scanning, "cameras": worker.cameras,
                        "current": worker.get_settings()["camera"]})

    @app.post("/api/cameras/scan")
    def scan_cameras():
        worker.request_scan()
        return jsonify({"scanning": True})

    @app.get("/camera/<int:index>/thumb.jpg")
    def camera_thumb(index: int):
        thumb = worker.thumbs.get(index)
        if thumb is None:
            abort(404)
        return Response(thumb, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/stats")
    def stats():
        with worker.new_frame:
            data = dict(worker.stats)
        data["events"] = list(worker.events)
        data["settings"] = s = worker.get_settings()
        data["alert_labels"] = sorted(worker.alerter.labels) if worker.alerter else []
        data["voice_labels"] = sorted(worker.voice.labels) if worker.voice else []
        data["telegram"] = worker.alerter is not None
        data["voice_available"] = bool(worker.voice and worker.voice.available)
        return jsonify(data)

    @app.get("/api/objects")
    def objects():
        """All objects the loaded model knows, for the alert object picker."""
        known = worker.detector.labels
        return jsonify(sorted(({"key": k, "ms": translate(k, "ms"), "en": k} for k in known),
                              key=lambda o: o["ms"]))

    @app.post("/api/test-voice")
    def test_voice():
        if not (worker.voice and worker.voice.available):
            return jsonify({"ok": False, "error": "voice not available"}), 400
        worker.voice.lang = worker.get_settings()["lang"]
        worker.voice.test()
        return jsonify({"ok": True})

    @app.post("/api/telegram/photo")
    def telegram_photo():
        if not worker.alerter:
            return jsonify({"ok": False, "error": "Telegram not set up"}), 400
        if worker.jpeg is None:
            return jsonify({"ok": False, "error": "no image"}), 503
        counts = worker.stats.get("counts", [])
        things = ", ".join(f"{n} x {name}" for name, n in counts) or ui("nothing", worker.get_settings()["lang"])
        caption = f"📸 {datetime.now():%H:%M:%S} · {things} (from web page)"
        ok = worker.alerter.client.send_photo(worker.jpeg, caption).get("ok", False)
        return jsonify({"ok": ok}), (200 if ok else 502)

    @app.post("/api/settings")
    def settings():
        body = request.get_json(silent=True) or {}
        changes = {}
        try:
            if "camera" in body:
                changes["camera"] = min(max(int(body["camera"]), 0), 9)
            if "lang" in body and body["lang"] in ("ms", "en"):
                changes["lang"] = body["lang"]
            if "conf" in body:
                changes["conf"] = min(max(float(body["conf"]), 0.05), 0.95)
            if "text_size" in body:
                changes["text_size"] = min(max(float(body["text_size"]), 0.5), 3.0)
            if "alerts" in body and worker.alerter:
                changes["alerts"] = bool(body["alerts"])
            if "voice" in body and worker.voice:
                changes["voice"] = bool(body["voice"])
            if "clip" in body:
                changes["clip"] = bool(body["clip"])
            if "alert_labels" in body and worker.alerter:
                worker.alerter.labels = {l for l in body["alert_labels"] if l in worker.detector.labels}
            if "voice_labels" in body and worker.voice:
                worker.voice.labels = {l for l in body["voice_labels"] if l in worker.detector.labels}
        except (TypeError, ValueError):
            abort(400)
        return jsonify(worker.update(**changes))

    return app


def lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is actually sent
            return s.getsockname()[0]
    except OSError:
        return None


def main():
    p = argparse.ArgumentParser(description="Object detection in the browser")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--model", default="yolo11n.pt")
    p.add_argument("--conf", type=float, default=0.5)
    p.add_argument("--device", default=None, help="'mps' (Apple GPU), 'cpu', or 'cuda'")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--lang", choices=["en", "ms"], default="en", help="label language: en = English (default), ms = Malay")
    p.add_argument("--text-size", type=float, default=1.0)
    p.add_argument("--alert", help="send a Telegram alert for these objects, e.g. \"teddy bear,cow\"")
    p.add_argument("--alert-cooldown", type=float, default=60,
                   help="seconds to wait before alerting again for the same object (default 60)")
    p.add_argument("--clip-seconds", type=float, default=5,
                   help="length of the video clip sent with each alert (0 = photo only)")
    p.add_argument("--voice", help="speak out loud for these objects, e.g. \"teddy bear\"")
    p.add_argument("--voice-cooldown", type=float, default=10,
                   help="seconds before speaking again for the same object (default 10)")
    p.add_argument("--no-bot", action="store_true", help="do not listen for Telegram commands")
    p.add_argument("--no-login", action="store_true", help="open the page without a password")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--phone", action="store_true",
                   help="allow other devices on the same Wi-Fi to open the page")
    args = p.parse_args()

    print(f"Loading model {args.model} ...")
    detector = ObjectDetector(args.model, args.conf, args.device)
    print(f"Model knows {len(detector.labels)} objects")

    # Telegram + voice are always prepared, so they can be switched on from the web page later.
    client = TelegramClient.from_env(required=bool(args.alert))
    alert_labels = parse_labels(args.alert, "--alert", detector.labels) if args.alert else set()
    voice_labels = parse_labels(args.voice, "--voice", detector.labels) if args.voice else set()
    alerter = None
    if client:
        alerter = TelegramAlerter(alert_labels, args.alert_cooldown, args.lang,
                                  clip_seconds=args.clip_seconds, client=client)
        if alert_labels:
            print(f"Telegram alerts on for: {', '.join(sorted(alert_labels))}"
                  + (f" (photo + {args.clip_seconds:g}s video)" if args.clip_seconds > 0 else " (photo)"))
    voice = VoiceAnnouncer(voice_labels, args.voice_cooldown, args.lang)
    if voice_labels:
        print(f"Voice on for: {', '.join(sorted(voice_labels))}")

    # Login details come from .env so they are not written in the code.
    env = load_env()
    login = None
    if not args.no_login:
        if env.get("WEB_USERNAME") and env.get("WEB_PASSWORD"):
            login = (env["WEB_USERNAME"], env["WEB_PASSWORD"])
        else:
            print("  Note: no WEB_USERNAME / WEB_PASSWORD in .env - the page has no login.")
    secret_key = env.get("FLASK_SECRET_KEY")
    if not secret_key:
        secret_key = secrets.token_hex(32)
        save_env_value("FLASK_SECRET_KEY", secret_key)  # keeps you logged in after a restart

    worker = CameraWorker(detector, args.camera, args.width, args.height, args.lang, args.text_size,
                          alerter, voice, alerts_on=bool(alert_labels), voice_on=bool(voice_labels),
                          clip_seconds=args.clip_seconds)
    app = create_app(worker, login, secret_key)
    if client and not args.no_bot:
        TelegramBot(client, worker).start()

    host = "0.0.0.0" if args.phone else "127.0.0.1"
    print(f"\n  Open:  http://localhost:{args.port}")
    if args.phone:
        ip = lan_ip()
        if ip:
            print(f"  Phone (same Wi-Fi):  http://{ip}:{args.port}")
        print("  Note: anyone on this Wi-Fi network can open the page"
              + (" (a login is required)." if login else " and view the camera."))
    print("  Press Ctrl+C to stop.\n")
    app.run(host=host, port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
