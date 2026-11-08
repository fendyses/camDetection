"""Control camDetection from Telegram: /photo, /status, /on, /off, /camera, /voice, /help.

Only the chat ID saved in .env (TELEGRAM_CHAT_ID) is allowed to use the commands.
"""
import threading
from datetime import datetime

from cam_detection.telegram_alert import TelegramClient
from cam_detection.translations import translate

# (command, description shown in the Telegram menu)
COMMANDS = [
    ("help", "List all commands"),
    ("photo", "Send a photo from the camera now"),
    ("status", "What the camera sees right now"),
    ("on", "Turn Telegram alerts on"),
    ("off", "Turn Telegram alerts off"),
    ("camera", "List cameras / switch camera, e.g. /camera 1"),
    ("voice", "Voice alert: /voice on or /voice off"),
]

# Other names that also work (including the earlier Malay commands).
ALIASES = {"start": "help", "foto": "photo", "picture": "photo", "pic": "photo",
           "hidup": "on", "mati": "off", "kamera": "camera", "cam": "camera",
           "suara": "voice", "sound": "voice"}

HELP_TEXT = """🤖 camDetection - Commands

📸 /photo - Send a photo from the camera now
📊 /status - What the camera sees right now
🔔 /on - Turn Telegram alerts on
🔕 /off - Turn Telegram alerts off
🎥 /camera - List the available cameras
🔄 /camera 1 - Switch to camera 1
🔊 /voice on - Turn the voice alert on
🔇 /voice off - Turn the voice alert off
❓ /help - Show this list

Telegram alerts: {alerts}
Voice alert: {voice}"""


class TelegramBot:
    """Listens for commands in a background thread. `worker` is the web app's CameraWorker."""

    def __init__(self, client: TelegramClient, worker):
        self.client = client
        self.worker = worker
        self._offset: int | None = None

    def start(self) -> None:
        self.client.set_commands(COMMANDS)
        # Skip commands sent while the program was off, so old ones don't run now.
        old = self.client.get_updates(offset=-1, timeout=0)
        if old:
            self._offset = old[-1]["update_id"] + 1
        threading.Thread(target=self._loop, daemon=True).start()
        print("Telegram bot commands are on (send /help to your bot)")

    def _loop(self) -> None:
        while True:
            for update in self.client.get_updates(self._offset):
                self._offset = update["update_id"] + 1
                try:
                    self._handle(update.get("message") or {})
                except Exception as exc:  # never let one bad command stop the bot
                    print(f"[Telegram bot] error: {exc!r}")

    def _handle(self, msg: dict) -> None:
        text = (msg.get("text") or "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if not text.startswith("/") or not chat_id:
            return
        if chat_id != self.client.chat_id:
            self.client.send_message("⛔ Sorry, you are not allowed to use this bot.", chat_id=chat_id)
            print(f"[Telegram bot] ignored command from unknown chat {chat_id}")
            return

        parts = text.split()
        command = parts[0][1:].split("@")[0].lower()
        command = ALIASES.get(command, command)
        args = parts[1:]
        print(f"[Telegram bot] /{command} {' '.join(args)}".rstrip())

        handler = getattr(self, f"cmd_{command}", None)
        if handler is None:
            self.client.send_message(f"❓ Unknown command: {parts[0]}\nSend /help for the list of commands.")
        else:
            handler(args)

    # ---- helpers ------------------------------------------------------------

    def _lang(self) -> str:
        return self.worker.get_settings().get("lang", "en")

    def _alert_summary(self) -> str:
        alerter = self.worker.alerter
        if not alerter:
            return "not set up"
        names = ", ".join(translate(l, self._lang()) for l in sorted(alerter.labels)) or "no objects chosen"
        state = "🔔 ON" if self.worker.get_settings().get("alerts") else "🔕 OFF"
        return f"{state} - {names}"

    def _voice_summary(self) -> str:
        voice = getattr(self.worker, "voice", None)
        if not voice or not voice.available:
            return "not available"
        names = ", ".join(translate(l, self._lang()) for l in sorted(voice.labels)) or "no objects chosen"
        state = "🔊 ON" if self.worker.get_settings().get("voice") else "🔇 OFF"
        return f"{state} - {names}"

    def _objects_text(self) -> str:
        counts = self.worker.stats.get("counts", [])
        return ", ".join(f"{n} x {name}" for name, n in counts) or "nothing detected"

    # ---- commands -----------------------------------------------------------

    def cmd_help(self, args) -> None:
        self.client.send_message(HELP_TEXT.format(alerts=self._alert_summary(), voice=self._voice_summary()))

    def cmd_photo(self, args) -> None:
        jpeg = self.worker.jpeg
        if jpeg is None:
            self.client.send_message("⚠️ No picture from the camera right now.")
            return
        self.client.send_photo(jpeg, f"📸 {datetime.now():%H:%M:%S} · {self._objects_text()}")

    def cmd_status(self, args) -> None:
        stats, s = self.worker.stats, self.worker.get_settings()
        lines = [
            "📊 camDetection status",
            f"🕒 {datetime.now():%d/%m/%Y %H:%M:%S}",
            f"🎥 Camera {s['camera']} · {stats.get('resolution') or '-'} · {stats.get('fps', 0):.0f} FPS",
            f"👁️ Objects: {self._objects_text()}",
            f"🔔 Telegram alerts: {self._alert_summary()}",
            f"🔊 Voice alert: {self._voice_summary()}",
        ]
        if stats.get("error"):
            lines.append(f"❗ {stats['error']}")
        self.client.send_message("\n".join(lines))

    def _set_alerts(self, on: bool) -> None:
        if not self.worker.alerter:
            self.client.send_message("⚠️ Telegram alerts are not set up.")
            return
        self.worker.update(alerts=on)
        self.client.send_message(("🔔 Telegram alerts turned ON" if on else "🔕 Telegram alerts turned OFF")
                                 + f"\n{self._alert_summary()}")

    def cmd_on(self, args) -> None:
        self._set_alerts(True)

    def cmd_off(self, args) -> None:
        self._set_alerts(False)

    def cmd_voice(self, args) -> None:
        voice = getattr(self.worker, "voice", None)
        if not voice or not voice.available:
            self.client.send_message("⚠️ Voice is not available on this computer.")
            return
        choice = (args[0].lower() if args else "")
        if choice in ("on", "hidup"):
            self.worker.update(voice=True)
        elif choice in ("off", "mati"):
            self.worker.update(voice=False)
        elif choice:
            self.client.send_message("⚠️ Example: /voice on  or  /voice off")
            return
        self.client.send_message(f"🔊 Voice alert: {self._voice_summary()}")

    def cmd_camera(self, args) -> None:
        cams = self.worker.cameras
        current = self.worker.get_settings()["camera"]
        if not args:
            if not cams:
                self.client.send_message("⚠️ No cameras found.")
                return
            lines = ["🎥 Available cameras:"]
            for c in cams:
                mark = " ✅ (in use)" if c["index"] == current else ""
                dark = " · dark" if c["dark"] else ""
                lines.append(f"• Camera {c['index']}{dark}{mark}")
            lines.append("\nSwitch camera: /camera 1")
            self.client.send_message("\n".join(lines))
            return
        try:
            index = int(args[0])
        except ValueError:
            self.client.send_message("⚠️ Example: /camera 1")
            return
        if cams and index not in [c["index"] for c in cams]:
            available = ", ".join(str(c["index"]) for c in cams)
            self.client.send_message(f"⚠️ Camera {index} not found. Available cameras: {available}")
            return
        self.worker.update(camera=index)
        self.client.send_message(f"🔄 Switched to camera {index}. Send /photo to see it.")
