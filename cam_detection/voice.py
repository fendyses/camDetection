"""Speak out loud when chosen objects are detected on macOS or Windows."""
import os
import shutil
import subprocess
import sys
import time

from cam_detection.translations import translate

MACOS_VOICES = {"en": "Samantha", "ms": "Amira"}
WINDOWS_CULTURES = {"en": "en-US", "ms": "ms-MY"}
WINDOWS_SPEECH_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$culture = $env:CAM_VOICE_CULTURE; $text = $env:CAM_VOICE_TEXT; "
    "$voice = $speaker.GetInstalledVoices() | "
    "Where-Object { $_.VoiceInfo.Culture.Name -eq $culture } | Select-Object -First 1; "
    "if ($voice) { $speaker.SelectVoice($voice.VoiceInfo.Name) }; "
    "$speaker.Speak($text)"
)


class VoiceAnnouncer:
    def __init__(self, labels: set[str], cooldown: float = 10, lang: str = "en"):
        self.labels = labels
        self.cooldown = cooldown
        self.lang = lang
        self._engine = None
        self._executable = None
        if sys.platform == "darwin":
            self._engine = "macos"
            self._executable = shutil.which("say")
        elif sys.platform == "win32":
            self._engine = "windows"
            self._executable = shutil.which("powershell.exe") or shutil.which("powershell")
        self.available = self._executable is not None
        self.enabled = True
        if not self.available:
            print("[Suara] No supported speech engine was found - voice is off.")
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
        try:
            env = None
            if self._engine == "macos":
                voice = MACOS_VOICES.get(self.lang, MACOS_VOICES["en"])
                command = [self._executable, "-v", voice, text]
            else:
                culture = WINDOWS_CULTURES.get(self.lang, WINDOWS_CULTURES["en"])
                command = [self._executable, "-NoProfile", "-NonInteractive", "-Command",
                           WINDOWS_SPEECH_SCRIPT]
                # -Command does not bind extra arguments to $args, so pass via environment.
                env = {**os.environ, "CAM_VOICE_CULTURE": culture, "CAM_VOICE_TEXT": text}
            self._process = subprocess.Popen(
                command,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            print(f"[Suara] could not speak: {exc}")
