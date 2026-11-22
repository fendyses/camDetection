"""Blink a light on an ESP32 over the USB cable.

The app sends one line every half second: "ON" (blink) or "OFF" (light off).
The ESP32 sketch in esp32/cow_light/ blinks while it keeps hearing "ON" and
switches the light off by itself if the messages stop (app closed, cable pulled).
"""
import sys
import threading
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pyserial not installed
    serial = None
    list_ports = None

BAUD = 115200
SEND_EVERY = 0.5   # seconds between messages (also the "still alive" heartbeat)
RETRY_EVERY = 3.0  # seconds between reconnect attempts
# USB-to-serial chips used on ESP32 boards: Silicon Labs CP210x, WCH CH340/CH9102, FTDI, Espressif native USB.
ESP_VENDOR_IDS = {0x10C4, 0x1A86, 0x0403, 0x303A}
ESP_PORT_NAMES = ("usbserial", "SLAB_USBtoUART", "wchusbserial", "usbmodem")


def find_port() -> str | None:
    """Return the serial port of a plugged-in ESP32, or None."""
    if list_ports is None:
        return None
    for port in list_ports.comports():
        if port.vid in ESP_VENDOR_IDS:
            return _callout(port.device)
    for port in list_ports.comports():
        if any(name in port.device for name in ESP_PORT_NAMES):
            return _callout(port.device)
    return None


def _callout(device: str) -> str:
    # On macOS use /dev/cu.* (does not wait for a modem carrier like /dev/tty.* does).
    return device.replace("/dev/tty.", "/dev/cu.") if sys.platform == "darwin" else device


class EspLight:
    """Keeps the ESP32 light in step with `active`. Light is OFF by default."""

    def __init__(self, port: str = "auto", hold: float = 3.0):
        self.port_setting = port
        self.hold = hold              # keep blinking this many seconds after the cow leaves the road
        self.enabled = True
        self.port: str | None = None
        self.connected = False
        self.blinking = False
        self._last_seen = 0.0         # last time a cow was on the road
        self._test_until = 0.0        # "Test light" button: blink until this time
        self._serial = None
        self._lock = threading.Lock()
        self.available = serial is not None
        if not self.available:
            print("[ESP32] pyserial is not installed - the light is off. Run:  pip install pyserial")
            return
        threading.Thread(target=self._loop, daemon=True).start()

    def update(self, on_road: bool) -> None:
        """Call once per frame with whether an alert object is on the road."""
        now = time.time()
        with self._lock:
            if on_road:
                self._last_seen = now
            self.blinking = self._should_blink(now)

    def test(self, seconds: float = 5) -> None:
        """Blink for a few seconds (even when switched off) so you can check the wiring."""
        with self._lock:
            self._test_until = time.time() + seconds
            self.blinking = True

    def _should_blink(self, now: float) -> bool:
        return now < self._test_until or (self.enabled and now - self._last_seen <= self.hold)

    def status(self) -> dict:
        return {"available": self.available, "connected": self.connected, "port": self.port,
                "blinking": self.blinking, "enabled": self.enabled}

    def _connect(self) -> bool:
        port = find_port() if self.port_setting == "auto" else self.port_setting
        if not port:
            return False
        try:
            s = serial.Serial()
            s.port, s.baudrate, s.timeout, s.write_timeout = port, BAUD, 0, 1
            s.dtr = s.rts = False  # don't hold the ESP32 in reset
            s.open()
        except (serial.SerialException, OSError) as exc:
            print(f"[ESP32] could not open {port}: {exc}")
            return False
        self._serial, self.port, self.connected = s, port, True
        print(f"[ESP32] connected on {port}")
        return True

    def _loop(self):
        while True:
            if not self.connected and not self._connect():
                time.sleep(RETRY_EVERY)
                continue
            with self._lock:
                self.blinking = self._should_blink(time.time())
                message = b"ON\n" if self.blinking else b"OFF\n"
            try:
                self._serial.write(message)
                self._serial.reset_input_buffer()  # ignore what the board prints
            except (serial.SerialException, OSError) as exc:
                print(f"[ESP32] disconnected: {exc}")
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial, self.connected = None, False
                continue
            time.sleep(SEND_EVERY)
