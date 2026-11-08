"""Speak out loud when chosen objects are detected. macOS only."""
import shutil
import subprocess
import time

from cam_detection.translations import translate

VOICES = {"en": "Samantha", "ms": "Amira"}  # built-in macOS voices


class VoiceAnnouncer:
    def __init__(self, labels: set[str], cooldown: float = 10, lang: str = "en"):
        self.labels = labels
        self.cooldown = cooldown
        self.lang = lang
        self.available = shutil.which("say") is not None
        self.enabled = True
        if not self.available:
            print("[Suara] The 'say' command is not available (macOS only) - voice is off.")
        self._last_spoken: dict[str, float] = {}
        self._process: subprocess.Popen | None = None

    def check(self, detections) -> None:
        """Call once per frame. Speaks (without blocking) if a chosen object is seen."""
        if not (self.enabled and self.available and self.labels):
            return
        if self._process is not None and self._process.poll() is None:
            return  # still speaking
        now = time.time()
        found: dict[str, int] = {}
        for d in detections:
            if d.label in self.labels:
                found[d.label] = found.get(d.label, 0) + 1
        due = {l: n for l, n in found.items() if now - self._last_spoken.get(l, 0) >= self.cooldown}
        if not due:
            return
        for label in due:
            self._last_spoken[label] = now
        self.say(self._sentence(due))

    def _sentence(self, found: dict[str, int]) -> str:
        if self.lang == "ms":
            things = " dan ".join(
                translate(l, "ms") if n == 1 else f"{n} {translate(l, 'ms')}" for l, n in found.items())
            return f"Amaran! {things} dikesan."
        things = " and ".join(
            translate(l, "en") if n == 1 else f"{n} {translate(l, 'en')}s" for l, n in found.items())
        return f"Alert! {things[:1].upper()}{things[1:]} detected."

    def test(self) -> None:
        """Speak a sample sentence (for the 'test voice' button)."""
        labels = sorted(self.labels) or ["teddy bear"]
        self.say(self._sentence({labels[0]: 1}))

    def say(self, text: str) -> None:
        if not self.available:
            return
        voice = VOICES.get(self.lang, VOICES["en"])
        try:
            self._process = subprocess.Popen(["say", "-v", voice, text])
        except OSError as exc:
            print(f"[Suara] could not speak: {exc}")
