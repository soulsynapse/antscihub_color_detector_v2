# core/color_store.py
import json
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal


class ColorStore(QObject):
    colors_changed = pyqtSignal()
    bounds_changed = pyqtSignal()
    detection_settings_changed = pyqtSignal()

    DEFAULT_BOUNDS = {
        "H": (0, 179),
        "S": (0, 255),
        "V": (0, 255),
    }

    def __init__(self):
        super().__init__()
        self._colors = []
        self._bounds = {k: list(v) for k, v in self.DEFAULT_BOUNDS.items()}
        self._min_area = 1
        self._merge_distance = 0

    @property
    def min_area(self):
        return self._min_area

    @min_area.setter
    def min_area(self, value):
        value = max(1, int(value))
        if value != self._min_area:
            self._min_area = value
            self.detection_settings_changed.emit()

    @property
    def merge_distance(self):
        return self._merge_distance

    @merge_distance.setter
    def merge_distance(self, value):
        value = max(0, int(value))
        if value != self._merge_distance:
            self._merge_distance = value
            self.detection_settings_changed.emit()

    def add_color_bgr(self, bgr: np.ndarray):
        bgr = np.array(bgr, dtype=np.uint8)
        pixel = bgr.reshape(1, 1, 3)
        hsv = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV).flatten()
        color_data = {
            "BGR": bgr.copy(),
            "H": int(hsv[0]),
            "S": int(hsv[1]),
            "V": int(hsv[2]),
        }
        self._colors.append(color_data)
        self.colors_changed.emit()

    def add_color_region(self, frame_bgr: np.ndarray, center_x: int, center_y: int, radius: int = 5):
        h, w = frame_bgr.shape[:2]
        x_min = max(0, center_x - radius)
        x_max = min(w - 1, center_x + radius)
        y_min = max(0, center_y - radius)
        y_max = min(h - 1, center_y + radius)

        region = frame_bgr[y_min : y_max + 1, x_min : x_max + 1]
        if region.size == 0:
            return

        region_hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        new_colors = []
        for ry in range(region.shape[0]):
            for rx in range(region.shape[1]):
                bgr = region[ry, rx]
                hsv = region_hsv[ry, rx]
                color_data = {
                    "BGR": bgr.copy(),
                    "H": int(hsv[0]),
                    "S": int(hsv[1]),
                    "V": int(hsv[2]),
                }
                new_colors.append(color_data)

        self._colors.extend(new_colors)
        self.colors_changed.emit()

    def remove_color(self, index: int):
        if 0 <= index < len(self._colors):
            self._colors.pop(index)
            self.colors_changed.emit()

    def clear_colors(self):
        self._colors.clear()
        self.colors_changed.emit()

    def get_all_colors(self) -> list:
        return list(self._colors)

    def get_bounds(self) -> dict:
        return {k: tuple(v) for k, v in self._bounds.items()}

    def set_bound(self, channel: str, lo: int, hi: int):
        if channel in self._bounds:
            lo = int(lo)
            hi = int(hi)
            old = tuple(self._bounds[channel])
            self._bounds[channel] = [lo, hi]
            if (lo, hi) != old:
                self.bounds_changed.emit()

    def has_any_bounds(self) -> bool:
        for k, v in self._bounds.items():
            default = self.DEFAULT_BOUNDS[k]
            if v[0] != default[0] or v[1] != default[1]:
                return True
        return False

    def is_color_in_bounds(self, color_data: dict) -> bool:
        bounds = self.get_bounds()
        for channel in ["S", "V"]:
            lo, hi = bounds[channel]
            default = self.DEFAULT_BOUNDS[channel]
            if lo == default[0] and hi == default[1]:
                continue
            val = color_data[channel]
            if val < lo or val > hi:
                return False

        h_lo, h_hi = bounds["H"]
        h_default = self.DEFAULT_BOUNDS["H"]
        if h_lo != h_default[0] or h_hi != h_default[1]:
            h_val = color_data["H"]
            if h_lo <= h_hi:
                if h_val < h_lo or h_val > h_hi:
                    return False
            else:
                if h_val < h_lo and h_val > h_hi:
                    return False
        return True

    def reset_bounds(self):
        for k, v in self.DEFAULT_BOUNDS.items():
            self._bounds[k] = list(v)
        self.bounds_changed.emit()

    def export_settings(self) -> dict:
        colors = []
        for c in self._colors:
            bgr = c["BGR"]
            colors.append(
                {
                    "BGR": [int(bgr[0]), int(bgr[1]), int(bgr[2])],
                    "H": int(c["H"]),
                    "S": int(c["S"]),
                    "V": int(c["V"]),
                }
            )

        return {
            "version": 1,
            "bounds": {k: [int(v[0]), int(v[1])] for k, v in self._bounds.items()},
            "min_area": int(self.min_area),
            "merge_distance": int(self.merge_distance),
            "colors": colors,
        }

    def save_settings(self, path: str) -> tuple[bool, str]:
        try:
            out_path = Path(path)
            payload = self.export_settings()
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return True, f"Saved settings to {out_path.name}"
        except Exception as exc:
            return False, f"Save failed: {exc}"

    def load_settings(self, path: str) -> tuple[bool, str]:
        # Parse everything before touching state so a bad file leaves the store unchanged.
        try:
            in_path = Path(path)
            payload = json.loads(in_path.read_text(encoding="utf-8"))

            bounds = {}
            for k, default in self.DEFAULT_BOUNDS.items():
                lo, hi = payload["bounds"][k]
                lo, hi = int(lo), int(hi)
                if not (default[0] <= lo <= default[1] and default[0] <= hi <= default[1]):
                    raise ValueError(f"{k} bounds {lo}-{hi} outside {default[0]}-{default[1]}")
                if k != "H" and lo > hi:
                    raise ValueError(f"{k} bounds {lo}-{hi} are reversed (only H may wrap)")
                bounds[k] = [lo, hi]

            min_area = max(1, int(payload.get("min_area", 1)))
            merge_distance = max(0, int(payload.get("merge_distance", 0)))

            colors = []
            for c in payload.get("colors", []):
                bgr = np.array(c["BGR"], dtype=np.uint8)
                if bgr.shape != (3,):
                    raise ValueError(f"bad BGR entry: {c['BGR']}")
                colors.append({"BGR": bgr, "H": int(c["H"]), "S": int(c["S"]), "V": int(c["V"])})
        except Exception as exc:
            return False, f"Load failed: {exc}"

        self._bounds = bounds
        self._min_area = min_area
        self._merge_distance = merge_distance
        self._colors = colors
        self.colors_changed.emit()
        self.bounds_changed.emit()
        self.detection_settings_changed.emit()
        return True, f"Loaded settings from {in_path.name}"
