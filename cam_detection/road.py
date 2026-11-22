"""Find the road by its colour and tell whether a detected object is standing on it.

Asphalt looks dark grey: almost no colour and not too bright. "Colour" here is
the gap between the strongest and weakest of red/green/blue (0 = pure grey). That
is steadier than HSV saturation, which jumps around in dark pixels and under a
tinted camera.
Grass, soil, sky and most walls have more colour or are brighter, so a simple
colour test finds the road without drawing a zone - it keeps working when the
camera is moved.

An object counts as "on the road" when the ground around its feet (the bottom
edge of its box) is mostly road. The object's own box is left out of that test,
so a black cow is not mistaken for road.
"""
from dataclasses import dataclass

import cv2
import numpy as np

WORK_WIDTH = 320  # the colour test runs on a small copy of the frame (fast)


@dataclass
class RoadSettings:
    max_colour: int = 15       # 0-255: any pixel this grey counts (0 = pure grey)
    max_ratio: float = 0.50    # or: colour at most this share of its brightness (handles lighting / camera tint)...
    max_green: float = 0.25    # ...and green not standing out by more than this share (grass is ~0.4-0.6)
    min_brightness: int = 15   # 0-255: below this is treated as pure black, not road
    max_brightness: int = 200  # 0-255: above this is too light to be asphalt
    min_share: float = 0.30    # share of road pixels around the feet needed for "on the road"
    min_area: float = 0.02     # road patches smaller than this share of the picture are ignored
    min_grain: float = 2.2     # asphalt texture: local brightness variation in % (smooth walls/metal ~1-2)
    thin_share: float = 0.6    # strips narrower than this share of the road's width are dropped (rails)


def _grain(frame: np.ndarray, out_shape) -> np.ndarray:
    """Surface texture (%) at twice the work resolution, shrunk to `out_shape` (rows, cols)."""
    h, w = frame.shape[:2]
    width = WORK_WIDTH * 2
    grey = cv2.cvtColor(cv2.resize(frame, (width, max(1, int(h * width / w))), interpolation=cv2.INTER_AREA),
                        cv2.COLOR_BGR2GRAY).astype(np.float32)
    mean = cv2.blur(grey, (5, 5))
    spread = np.sqrt(np.maximum(cv2.blur(grey * grey, (5, 5)) - mean * mean, 0))
    grain = spread / np.maximum(mean, 1) * 100
    return cv2.resize(grain, (out_shape[1], out_shape[0]), interpolation=cv2.INTER_AREA)


def road_mask(frame: np.ndarray, settings: RoadSettings, ignore_boxes=()) -> np.ndarray:
    """Return a small 0/255 mask of the road (WORK_WIDTH pixels wide)."""
    h, w = frame.shape[:2]
    scale = WORK_WIDTH / w
    small = cv2.resize(frame, (WORK_WIDTH, max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    brightest, darkest = small.max(axis=2), small.min(axis=2)
    colour = brightest - darkest  # uint8, never negative
    b, g, r = (small[..., i].astype(np.float32) for i in range(3))
    green = (g - np.maximum(r, b)) / np.maximum(g, 1)  # how much green stands out (grass)
    greyish = (colour <= settings.max_colour) | (
        (colour <= settings.max_ratio * brightest.astype(np.float32)) & (green <= settings.max_green))
    # Asphalt is grainy; walls, cardboard, glass and painted metal are smooth.
    grainy = _grain(frame, small.shape[:2]) >= settings.min_grain
    mask = (greyish & grainy & (brightest >= settings.min_brightness)
            & (brightest <= settings.max_brightness)).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)   # remove specks
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)  # fill small gaps (grain, road markings)
    # Rails, fences and kerbs are thin strips; the road is wide. Remove anything
    # much thinner than the widest grey area in the picture.
    thickest = cv2.distanceTransform(mask, cv2.DIST_L2, 5).max()  # half-width of the widest area
    size = int(np.clip(thickest * settings.thin_share, 5, 21)) | 1
    if size > 5:
        thin = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, thin)
    # Keep only big patches - a dark rock or tyre is not a road. This is judged
    # before the objects are cut out, so a cow covering part of a narrow road
    # does not break the road into "too small" pieces.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_pixels = settings.min_area * mask.size
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_pixels
    mask = np.where(keep[labels], 255, 0).astype(np.uint8)
    # Detected objects are not road (a black cow must not look like asphalt).
    for x1, y1, x2, y2 in ignore_boxes:
        mask[int(y1 * scale):int(y2 * scale) + 1, int(x1 * scale):int(x2 * scale) + 1] = 0
    return mask


def feet_share(box, mask: np.ndarray, frame_width: int, boxes=()) -> float:
    """Share (0-1) of road pixels in a band around the bottom edge of `box`."""
    scale = mask.shape[1] / frame_width
    x1, y1, x2, y2 = (v * scale for v in box)
    bw, bh = max(x2 - x1, 1), max(y2 - y1, 1)
    mh, mw = mask.shape
    top, bottom = int(max(y2 - 0.15 * bh, 0)), int(min(y2 + 0.15 * bh, mh - 1))
    left, right = int(max(x1 - 0.3 * bw, 0)), int(min(x2 + 0.3 * bw, mw - 1))
    if bottom <= top or right <= left:
        return 0.0
    band = mask[top:bottom + 1, left:right + 1] > 0
    # Only judge the ground, not the pixels covered by detected objects.
    ground = np.ones_like(band)
    for b in boxes:
        bx1, by1, bx2, by2 = (int(v * scale) for v in b)
        ground[max(by1 - top, 0):max(by2 - top + 1, 0), max(bx1 - left, 0):max(bx2 - left + 1, 0)] = False
    if ground.sum() < 10:  # object fills the whole band - fall back to the strip just below it
        strip = mask[min(int(y2) + 1, mh - 1):min(int(y2 + 0.1 * bh) + 2, mh), left:right + 1]
        return float((strip > 0).mean()) if strip.size else 0.0
    return float(band[ground].mean())


class RoadChecker:
    """Works out, per frame, which detections are on the road."""

    def __init__(self, settings: RoadSettings | None = None):
        self.settings = settings or RoadSettings()
        self.mask: np.ndarray | None = None  # last road mask (for the overlay)

    def on_road(self, frame: np.ndarray, detections) -> set[int]:
        """Return the indexes of `detections` that stand on the road."""
        boxes = [d.box for d in detections]
        self.mask = road_mask(frame, self.settings, boxes)
        w = frame.shape[1]
        return {i for i, d in enumerate(detections)
                if feet_share(d.box, self.mask, w, boxes) >= self.settings.min_share}

    def draw_overlay(self, frame: np.ndarray) -> None:
        """Tint the detected road light blue (in place) so you can check the colour test."""
        if self.mask is None:
            return
        h, w = frame.shape[:2]
        big = cv2.resize(self.mask, (w, h), interpolation=cv2.INTER_NEAREST) > 0
        tint = np.array((255, 160, 60), dtype=np.float32)  # BGR light blue
        frame[big] = (frame[big] * 0.6 + tint * 0.4).astype(np.uint8)
