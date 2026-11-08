"""Thin wrapper around a YOLO model for per-frame object detection."""
import os
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cam_detection.translations import translate, ui
from ultralytics import YOLO


@dataclass
class Detection:
    label: str
    confidence: float
    box: tuple[int, int, int, int]  # x1, y1, x2, y2


class ObjectDetector:
    def __init__(self, model_path: str = "yolo11n.pt", confidence: float = 0.5, device: str | None = None):
        # The model weights are downloaded automatically on first use.
        self.model = YOLO(model_path)
        self.confidence = confidence
        self.device = device
        # All object names this model knows, lower-case (e.g. "teddy bear", "goat").
        self.labels: set[str] = {name.lower() for name in self.model.names.values()}

    def detect(self, frame: np.ndarray) -> list[Detection]:
        result = self.model.predict(frame, conf=self.confidence, device=self.device, verbose=False)[0]
        detections = []
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cls_id = int(box.cls[0])
            detections.append(Detection(result.names[cls_id].lower(), float(box.conf[0]), (x1, y1, x2, y2)))
        return detections


# Bright, easy-to-tell-apart colours (RGB).
PALETTE = [
    (255, 99, 71), (30, 144, 255), (50, 205, 50), (255, 165, 0), (186, 85, 211),
    (0, 206, 209), (255, 20, 147), (154, 205, 50), (255, 215, 0), (100, 149, 237),
]

_FONT_CANDIDATES = [
    ("/System/Library/Fonts/Avenir Next.ttc", 2),  # Avenir Next Demi Bold (macOS)
    ("/System/Library/Fonts/Helvetica.ttc", 1),
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
    ("DejaVuSans-Bold.ttf", 0),  # Linux
    (str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arialbd.ttf"), 0),
    ("arialbd.ttf", 0),  # Windows fallback
]
_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _font_cache:
        for path, index in _FONT_CANDIDATES:
            try:
                _font_cache[size] = ImageFont.truetype(path, size, index=index)
                break
            except OSError:
                continue
        else:
            _font_cache[size] = ImageFont.load_default(size)
    return _font_cache[size]


def _color_for(label: str) -> tuple[int, int, int]:
    return PALETTE[zlib.crc32(label.encode()) % len(PALETTE)]


ALERT_RED = (255, 35, 35)  # RGB
BLINK_SECONDS = 0.35       # how long each on/off phase of the flashing lasts


def draw_detections(frame: np.ndarray, detections: list[Detection], fps: float | None = None,
                    text_scale: float = 1.0, lang: str = "en",
                    highlight: set[str] | frozenset = frozenset()) -> np.ndarray:
    """Draw boxes and smooth, readable labels onto a BGR frame (in place) and return it.

    Objects whose label is in `highlight` get a bigger, flashing red box.
    """
    h, w = frame.shape[:2]
    unit = max(h, w) / 1280 * text_scale        # scale everything with the picture size
    font_size = max(14, int(32 * unit))
    thickness = max(2, int(3 * unit))
    pad = max(4, int(8 * unit))

    blink_on = int(time.time() / BLINK_SECONDS) % 2 == 0
    grow = max(6, int(14 * unit))  # how much bigger the alert box is than the object

    def box_of(det: Detection) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = det.box
        if det.label in highlight:
            return max(x1 - grow, 0), max(y1 - grow, 0), min(x2 + grow, w - 1), min(y2 + grow, h - 1)
        return x1, y1, x2, y2

    # 1) Boxes with OpenCV (fast).
    red_bgr = ALERT_RED[::-1]
    for det in detections:
        x1, y1, x2, y2 = box_of(det)
        if det.label in highlight:
            if blink_on:
                # Red glow inside the box + a thick bright border.
                roi = frame[y1:y2 + 1, x1:x2 + 1]
                cv2.addWeighted(roi, 0.72, np.full_like(roi, red_bgr), 0.28, 0, dst=roi)
                cv2.rectangle(frame, (x1, y1), (x2, y2), red_bgr, thickness * 3, lineType=cv2.LINE_AA)
            else:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 150), thickness, lineType=cv2.LINE_AA)
        else:
            r, g, b = _color_for(det.label)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (b, g, r), thickness, lineType=cv2.LINE_AA)

    # 2) Text with Pillow (smooth TrueType font).
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img, "RGBA")
    font = _font(font_size)

    # Draw alert labels last so they sit on top of the others.
    for det in sorted(detections, key=lambda d: d.label in highlight):
        alert = det.label in highlight
        color = ALERT_RED if alert else _color_for(det.label)
        x1, y1, _, _ = box_of(det)
        name = translate(det.label, lang)
        if alert:
            text = f"{name.upper()}  {det.confidence:.0%}"
        else:
            text = f"{name[:1].upper()}{name[1:]}  {det.confidence:.0%}"
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        tw, th = r - l, b - t
        bw, bh = tw + pad * 2, th + pad * 2
        # Put the label above the box, or inside it if there is no room above.
        bx, by = x1, y1 - bh if y1 - bh >= 0 else y1
        bx = min(max(bx, 0), max(w - bw, 0))
        draw.rounded_rectangle((bx, by, bx + bw, by + bh), radius=pad, fill=color + (230,))
        draw.text((bx + pad - l, by + pad - t), text, font=font, fill=(255, 255, 255))

    # Info panel in the top-left corner.
    lines = []
    if fps is not None:
        lines.append(f"FPS  {fps:.0f}")
    lines.append(f"{ui('objects', lang)}  {len(detections)}")
    small = _font(max(12, int(font_size * 0.85)))
    line_h = small.getbbox("Ag")[3] + pad // 2
    panel_w = max(draw.textlength(s, font=small) for s in lines) + pad * 3
    panel_h = line_h * len(lines) + pad * 2
    draw.rounded_rectangle((pad, pad, pad + panel_w, pad + panel_h), radius=pad, fill=(0, 0, 0, 150))
    for i, s in enumerate(lines):
        draw.text((pad * 2.5, pad * 2 + i * line_h), s, font=small, fill=(255, 255, 255))

    frame[:] = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    return frame
