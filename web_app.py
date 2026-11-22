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

from cam_detection.camera import open_camera
from cam_detection.detector import ObjectDetector, draw_detections, parse_aliases
from cam_detection.esp_light import EspLight
from cam_detection.road import RoadChecker, RoadSettings
from cam_detection.telegram_alert import (TelegramAlerter, TelegramClient, load_env, parse_labels,
                                          save_env_value)
from cam_detection.telegram_bot import TelegramBot
from cam_detection.voice import VoiceAnnouncer
from cam_detection.translations import translate, ui

WEB_DIR = Path(__file__).parent / "web"
BOOT_ID = secrets.token_hex(4)  # changes on every restart, so the page knows to reconnect the video
MAX_CAMERAS = 6          # camera numbers 0..5 are checked when scanning
THUMB_WIDTH = 320        # preview picture width in the camera picker
DARK_LEVEL = 12          # average brightness below this = "camera looks black"
STALL_SECONDS = 5        # no new picture for this long = camera has stopped
READ_TIMEOUT = 3         # a camera read that takes longer than this is treated as frozen


def make_thumb(frame) -> bytes:
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (THUMB_WIDTH, int(THUMB_WIDTH * h / w)))
    return cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()


class CameraWorker:
    """Reads the camera and runs detection in a background thread."""

    def __init__(self, detector: ObjectDetector, camera: int, width: int, height: int,
                 lang: str, text_size: float, alerter: TelegramAlerter | None = None,
                 voice: VoiceAnnouncer | None = None, alerts_on: bool = False,
                 voice_on: bool = False, clip_seconds: float = 5,
                 road: RoadChecker | None = None, light: EspLight | None = None):
        self.detector = detector
        self.road = road      # only objects on the road trigger alerts (None = everywhere)
        self.light = light    # ESP32 light that blinks while an alert object is on the road
        self.alerter = alerter
        self.voice = voice
        self.clip_seconds = clip_seconds
        self.width, self.height = width, height
        self.lock = threading.Lock()
        self.new_frame = threading.Condition()
        self.settings = {"camera": camera, "lang": lang, "conf": detector.confidence,
                         "text_size": text_size, "alerts": alerts_on and alerter is not None,
                         "voice": voice_on and voice is not None, "clip": clip_seconds > 0,
                         "road": road is not None, "show_road": False, "light": light is not None}
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
        self.last_frame_at = time.time()
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
        self._cap = open_camera(index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._opened = index
        return self._cap.isOpened()

    def _read(self):
        """Read one frame, but give up if the camera hangs (a frozen USB camera can block forever).

        Returns (ok, frame), or None when the read is stuck. A stuck read is left behind in its own
        thread and the camera is reopened, so switching camera or replugging still works.
        """
        result = {}
        cap = self._cap
        reader = threading.Thread(target=lambda: result.update(r=cap.read()), daemon=True)
        reader.start()
        reader.join(READ_TIMEOUT)
        return None if reader.is_alive() else result["r"]

    def request_scan(self):
        self.scanning = True

    def _scan(self):
        """Find which camera numbers work and take a preview picture from each."""
        if self._cap is not None:
            self._cap.release()
            self._cap, self._opened = None, None
        found, thumbs, misses = [], {}, 0
        for index in range(MAX_CAMERAS):
            cap = open_camera(index)
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

        got = self._read()
        if got is None:
            print(f"Camera {s['camera']} stopped responding - reopening it")
            self._cap, self._opened = None, None  # don't release: that can block on a frozen camera too
            self._set_error(f"Camera {s['camera']} stopped responding - unplug and replug it, then press Rescan")
            time.sleep(2)
            return
        ok, frame = got
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
        # Road rule: a chosen object only triggers when it stands on the (dark grey) road.
        on_road = None
        if self.road and s["road"]:
            on_road = self.road.on_road(frame, detections)
            if s["show_road"]:
                self.road.draw_overlay(frame)
        triggers = detections if on_road is None else [d for i, d in enumerate(detections) if i in on_road]
        watched = [d for d in detections if d.label in highlight]
        on_road_count = sum(d.label in highlight for d in triggers)
        draw_detections(frame, detections, fps=fps, text_scale=s["text_size"], lang=s["lang"],
                        highlight=highlight, on_road=on_road)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return
        if self.light:
            self.light.enabled = s["light"]
            self.light.update(on_road_count > 0)
        if self.voice:
            self.voice.lang = s["lang"]
            self.voice.enabled = s["voice"]
            self.voice.check(triggers)
        if self.alerter:
            self.alerter.enabled = s["alerts"]
            self.alerter.clip_seconds = (self.clip_seconds or 5) if s["clip"] else 0
            self.alerter.lang = s["lang"]
            self.alerter.check(triggers, buf.tobytes(), camera=s["camera"])

        counts = Counter(translate(d.label, s["lang"]) for d in detections).most_common()
        summary = ", ".join(f"{n} x {name}" for name, n in counts) or ui("nothing", s["lang"])
        if summary != state['last_summary']:
            self.events.appendleft({"time": datetime.now().strftime("%H:%M:%S"), "text": summary})
            state['last_summary'] = summary

        h, w = frame.shape[:2]
        self.last_frame_at = time.time()
        with self.new_frame:
            self.jpeg = buf.tobytes()
            self.frame_id += 1
            self.stats = {"fps": round(fps, 1), "total": len(detections), "counts": counts,
                          "error": None, "camera": s["camera"], "resolution": f"{w}x{h}",
                          "on_road": on_road_count, "off_road": len(watched) - on_road_count}
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
        # A frozen or unplugged camera can block without any error - say so on the page.
        stalled = time.time() - getattr(worker, "last_frame_at", time.time())
        if not data.get("error") and stalled > STALL_SECONDS and not getattr(worker, "scanning", False):
            data["error"] = (f"No picture from camera {worker.get_settings()['camera']} for {stalled:.0f}s - "
                             "unplug and replug the camera, then press Rescan")
        data["events"] = list(worker.events)
        data["boot"] = BOOT_ID
        data["settings"] = s = worker.get_settings()
        data["alert_labels"] = sorted(worker.alerter.labels) if worker.alerter else []
        data["voice_labels"] = sorted(worker.voice.labels) if worker.voice else []
        data["detection_labels"] = sorted(
            (worker.alerter.labels if worker.alerter else set())
            | (worker.voice.labels if worker.voice else set())
        )
        data["telegram"] = worker.alerter is not None
        data["voice_available"] = bool(worker.voice and worker.voice.available)
        data["road_available"] = getattr(worker, "road", None) is not None
        light = getattr(worker, "light", None)
        data["light"] = light.status() if light else None
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

    @app.post("/api/light/test")
    def light_test():
        light = getattr(worker, "light", None)
        if not (light and light.connected):
            return jsonify({"ok": False, "error": "ESP32 not connected"}), 400
        light.test(5)
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
            if "road" in body and getattr(worker, "road", None):
                changes["road"] = bool(body["road"])
            if "show_road" in body:
                changes["show_road"] = bool(body["show_road"])
            if "light" in body and getattr(worker, "light", None):
                changes["light"] = bool(body["light"])
            label_values = None
            if "detection_labels" in body:
                label_values = body["detection_labels"]
            elif "alert_labels" in body:
                label_values = body["alert_labels"]
            elif "voice_labels" in body:
                label_values = body["voice_labels"]
            if label_values is not None:
                labels = {l for l in label_values if l in worker.detector.labels}
                if worker.alerter:
                    worker.alerter.labels = set(labels)
                if worker.voice:
                    worker.voice.labels = set(labels)
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
    p.add_argument("--alert", help="add objects to the shared selection and enable Telegram alerts")
    p.add_argument("--alert-cooldown", type=float, default=60,
                   help="seconds to wait before alerting again for the same object (default 60)")
    p.add_argument("--clip-seconds", type=float, default=5,
                   help="length of the video clip sent with each alert (0 = photo only)")
    p.add_argument("--voice", help="add objects to the shared selection and enable voice alerts")
    p.add_argument("--voice-cooldown", type=float, default=10,
                   help="seconds before speaking again for the same object (default 10)")
    p.add_argument("--no-road", action="store_true",
                   help="alert wherever the object is (default: only when it is on the road)")
    p.add_argument("--road-max-colour", type=int, default=RoadSettings.max_colour,
                   help="road colour test: max colour 0-255, 0 = pure grey (higher = accept more tinted road)")
    p.add_argument("--road-ratio", type=float, default=RoadSettings.max_ratio,
                   help="road colour test: max colour as a share of brightness (higher = accept more tinted road)")
    p.add_argument("--road-min-bright", type=int, default=RoadSettings.min_brightness, help="road colour test: min brightness 0-255")
    p.add_argument("--road-max-bright", type=int, default=RoadSettings.max_brightness, help="road colour test: max brightness 0-255")
    p.add_argument("--road-share", type=float, default=RoadSettings.min_share,
                   help="share of road around the feet needed to count as on the road (default 0.30)")
    p.add_argument("--esp-port", default="auto",
                   help="ESP32 serial port, 'auto' to find it, or 'none' to switch the light off")
    p.add_argument("--light-hold", type=float, default=3,
                   help="seconds the light keeps blinking after the object leaves the road (default 3)")
    p.add_argument("--treat-as", default="dog=cow",
                   help="count one object as another, e.g. 'dog=cow' (default) or 'dog=cow,horse=cow'; '' = off")
    p.add_argument("--no-bot", action="store_true", help="do not listen for Telegram commands")
    p.add_argument("--no-login", action="store_true", help="open the page without a password")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--phone", action="store_true",
                   help="allow other devices on the same Wi-Fi to open the page")
    args = p.parse_args()

    print(f"Loading model {args.model} ...")
    detector = ObjectDetector(args.model, args.conf, args.device, aliases=parse_aliases(args.treat_as))
    print(f"Model knows {len(detector.labels)} objects")

    # Telegram + voice are always prepared, so they can be switched on from the web page later.
    client = TelegramClient.from_env(required=bool(args.alert))
    alert_labels = parse_labels(args.alert, "--alert", detector.labels) if args.alert else set()
    voice_labels = parse_labels(args.voice, "--voice", detector.labels) if args.voice else set()
    detection_labels = alert_labels | voice_labels
    alerter = None
    if client:
        alerter = TelegramAlerter(set(detection_labels), args.alert_cooldown, args.lang,
                                  clip_seconds=args.clip_seconds, client=client)
        if alert_labels:
            print(f"Telegram alerts on for: {', '.join(sorted(detection_labels))}"
                  + (f" (photo + {args.clip_seconds:g}s video)" if args.clip_seconds > 0 else " (photo)"))
    voice = VoiceAnnouncer(set(detection_labels), args.voice_cooldown, args.lang)
    if voice_labels:
        print(f"Voice on for: {', '.join(sorted(detection_labels))}")

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

    road = None
    if not args.no_road:
        road = RoadChecker(RoadSettings(max_colour=args.road_max_colour, max_ratio=args.road_ratio,
                                        min_brightness=args.road_min_bright,
                                        max_brightness=args.road_max_bright, min_share=args.road_share))
        print("Road rule on: chosen objects only trigger when they are on the road")
    light = None if args.esp_port.lower() == "none" else EspLight(args.esp_port, args.light_hold)

    worker = CameraWorker(detector, args.camera, args.width, args.height, args.lang, args.text_size,
                          alerter, voice, alerts_on=bool(alert_labels), voice_on=bool(voice_labels),
                          clip_seconds=args.clip_seconds, road=road, light=light)
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
