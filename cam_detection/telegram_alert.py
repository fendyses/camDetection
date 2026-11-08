"""Send Telegram alerts (photo + short video clip) when chosen objects are detected."""
import os
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import requests

from cam_detection.translations import LABELS_MS, translate

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    """Read KEY=value lines from .env (keys are upper-cased, quotes removed)."""
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip().upper()] = value.strip().strip('"').strip("'")
    return values


def save_env_value(key: str, value: str, path: Path = ENV_FILE) -> None:
    """Add or replace one KEY=value line in .env, keeping the other lines."""
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [l for l in lines if l.split("=", 1)[0].strip().upper() != key.upper()]
    lines.append(f'{key}="{value}"')
    path.write_text("\n".join(lines) + "\n")


def parse_labels(text: str, option: str = "--alert", known: set[str] | None = None) -> set[str]:
    """Turn 'orang,lembu' or 'person,cow' into the model's English class names.

    `known` = the object names of the loaded model (default: the 80 COCO objects).
    """
    known = known or set(LABELS_MS)
    ms_to_en: dict[str, str] = {}
    for en in sorted(known):
        ms_to_en.setdefault(translate(en, "ms"), en)
    labels = set()
    for part in text.split(","):
        name = part.strip().lower()
        if not name:
            continue
        if name in known:
            labels.add(name)
        elif name in ms_to_en:
            labels.add(ms_to_en[name])
        else:
            raise SystemExit(f"Unknown object for {option}: '{part.strip()}' - this model doesn't know it. "
                             f"Use names like: person, cow, car, cat, teddy bear")
    return labels


parse_alert_labels = parse_labels  # backwards-compatible name


class TelegramClient:
    """Small wrapper around the Telegram Bot API."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = str(chat_id)
        self.api = f"https://api.telegram.org/bot{token}"

    @classmethod
    def from_env(cls, required: bool = True) -> "TelegramClient | None":
        env = load_env()
        token = env.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = env.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
        if token and chat_id:
            return cls(token, chat_id)
        if not required:
            return None
        if not token:
            raise SystemExit("TELEGRAM_BOT_TOKEN is missing from .env")
        raise SystemExit("TELEGRAM_CHAT_ID is missing. Run:  python setup_telegram.py")

    def _post(self, method: str, timeout: float = 30, **kwargs) -> dict:
        try:
            r = requests.post(f"{self.api}/{method}", timeout=timeout, **kwargs)
            data = r.json()
            if not data.get("ok"):
                print(f"[Telegram] {method} failed: {data.get('description')}")
            return data
        except (requests.RequestException, ValueError) as exc:
            print(f"[Telegram] {method} error: {exc}")
            return {"ok": False}

    def send_message(self, text: str, chat_id=None) -> dict:
        return self._post("sendMessage", data={"chat_id": chat_id or self.chat_id, "text": text})

    def send_photo(self, jpeg: bytes, caption: str = "", chat_id=None) -> dict:
        return self._post("sendPhoto", data={"chat_id": chat_id or self.chat_id, "caption": caption},
                          files={"photo": ("foto.jpg", jpeg, "image/jpeg")})

    def send_video(self, mp4: bytes, caption: str = "", chat_id=None) -> dict:
        return self._post("sendVideo", timeout=120,
                          data={"chat_id": chat_id or self.chat_id, "caption": caption,
                                "supports_streaming": "true"},
                          files={"video": ("klip.mp4", mp4, "video/mp4")})

    def get_updates(self, offset: int | None, timeout: int = 25) -> list[dict]:
        params = {"timeout": timeout, "allowed_updates": '["message"]'}
        if offset is not None:
            params["offset"] = offset
        try:
            r = requests.get(f"{self.api}/getUpdates", params=params, timeout=timeout + 10)
            data = r.json()
            return data.get("result", []) if data.get("ok") else []
        except (requests.RequestException, ValueError):
            time.sleep(3)
            return []

    def set_commands(self, commands: list[tuple[str, str]]) -> None:
        import json
        self._post("setMyCommands", data={"commands": json.dumps(
            [{"command": c, "description": d} for c, d in commands])})


def make_clip(frames: list[tuple[float, bytes]], max_width: int = 960) -> bytes | None:
    """Turn (timestamp, jpeg) frames into an H.264 MP4 file (bytes)."""
    if len(frames) < 2:
        return None
    duration = frames[-1][0] - frames[0][0]
    fps = max(1.0, min(30.0, (len(frames) - 1) / max(duration, 0.1)))
    first = cv2.imdecode(np.frombuffer(frames[0][1], np.uint8), cv2.IMREAD_COLOR)
    h, w = first.shape[:2]
    if w > max_width:
        w, h = max_width, int(h * max_width / w) // 2 * 2
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "klip.mp4")
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"avc1"), fps, (w, h))
        if not writer.isOpened():  # fallback codec
            writer.release()
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        if not writer.isOpened():
            writer.release()
            print("[Telegram] video skipped: no compatible MP4 encoder is available")
            return None
        for _, jpeg in frames:
            img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if img.shape[1] != w or img.shape[0] != h:
                img = cv2.resize(img, (w, h))
            writer.write(img)
        writer.release()
        return Path(path).read_bytes()


class TelegramAlerter:
    """Sends a photo immediately, then a short video clip, when chosen objects appear."""

    def __init__(self, labels: set[str], cooldown: float = 60, lang: str = "en",
                 clip_seconds: float = 5, clip_before: float = 2,
                 client: TelegramClient | None = None):
        self.client = client or TelegramClient.from_env()
        self.labels = labels
        self.cooldown = cooldown
        self.lang = lang
        self.enabled = True
        self.clip_seconds = clip_seconds          # total clip length (0 = no video)
        self.clip_before = min(clip_before, clip_seconds)  # seconds before the alert
        self._last_sent: dict[str, float] = {}
        self._buffer: deque[tuple[float, bytes]] = deque()
        self._pending: list[dict] = []           # clips still collecting frames
        self._lock = threading.Lock()

    def check(self, detections, jpeg: bytes, camera=None) -> None:
        """Call once per frame with the annotated JPEG. Sends alerts in the background."""
        now = time.time()
        with self._lock:
            self._buffer.append((now, jpeg))
            self._finish_clips(now)

            due = {}
            if self.enabled:
                found: dict[str, int] = {}
                for d in detections:
                    if d.label in self.labels:
                        found[d.label] = found.get(d.label, 0) + 1
                due = {l: n for l, n in found.items() if now - self._last_sent.get(l, 0) >= self.cooldown}
                for label in due:
                    self._last_sent[label] = now

            if due:
                things = ", ".join(f"{n} x {translate(l, self.lang)}" for l, n in due.items())
                caption = self._caption(things, camera)
                threading.Thread(target=self._send_photo, args=(jpeg, caption, things), daemon=True).start()
                if self.clip_seconds > 0:
                    self._pending.append({"start": now - self.clip_before,
                                          "end": now + self.clip_seconds - self.clip_before,
                                          "caption": caption})

            # Keep only the frames still needed (pre-alert buffer + pending clips).
            keep_from = now - self.clip_before
            if self._pending:
                keep_from = min(keep_from, min(p["start"] for p in self._pending))
            while self._buffer and self._buffer[0][0] < keep_from:
                self._buffer.popleft()

    def _finish_clips(self, now: float) -> None:
        for clip in [p for p in self._pending if now >= p["end"]]:
            self._pending.remove(clip)
            frames = [(t, j) for t, j in self._buffer if clip["start"] <= t <= clip["end"]]
            threading.Thread(target=self._send_clip, args=(frames, clip["caption"]), daemon=True).start()

    def _caption(self, things: str, camera) -> str:
        when = datetime.now().strftime("%H:%M:%S")
        if self.lang == "ms":
            cam = f" · Kamera {camera}" if camera is not None else ""
            return f"⚠️ Amaran! {things} dikesan\n🕒 {when}{cam}"
        cam = f" · Camera {camera}" if camera is not None else ""
        return f"⚠️ Alert! {things} detected\n🕒 {when}{cam}"

    def _send_photo(self, jpeg: bytes, caption: str, things: str) -> None:
        if self.client.send_photo(jpeg, caption).get("ok"):
            print(f"[Telegram] photo sent: {things}")

    def _send_clip(self, frames, caption: str) -> None:
        mp4 = make_clip(frames)
        if not mp4:
            return
        label = "🎥 Video"
        secs = frames[-1][0] - frames[0][0]
        if self.client.send_video(mp4, f"{label} {secs:.0f}s · {caption}").get("ok"):
            print(f"[Telegram] video sent ({len(frames)} frames, {len(mp4) // 1024} KB)")
