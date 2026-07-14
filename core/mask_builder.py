# core/mask_builder.py (COMPLETE - HSV only)
import cv2
import numpy as np


def build_mask(frame_bgr: np.ndarray, bounds: dict, default_bounds: dict) -> np.ndarray:
    h, w = frame_bgr.shape[:2]
    mask = np.ones((h, w), dtype=np.uint8) * 255

    def is_narrowed(channel):
        lo, hi = bounds[channel]
        dlo, dhi = default_bounds[channel]
        return lo != dlo or hi != dhi

    if any(is_narrowed(c) for c in ('H', 'S', 'V')):
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        h_min, h_max = bounds['H']
        s_min, s_max = bounds['S']
        v_min, v_max = bounds['V']

        if h_min <= h_max:
            hsv_lower = np.array([h_min, s_min, v_min], dtype=np.uint8)
            hsv_upper = np.array([h_max, s_max, v_max], dtype=np.uint8)
            hsv_mask = cv2.inRange(hsv, hsv_lower, hsv_upper)
        else:
            hsv_lower1 = np.array([h_min, s_min, v_min], dtype=np.uint8)
            hsv_upper1 = np.array([179, s_max, v_max], dtype=np.uint8)
            hsv_lower2 = np.array([0, s_min, v_min], dtype=np.uint8)
            hsv_upper2 = np.array([h_max, s_max, v_max], dtype=np.uint8)
            hsv_mask = cv2.bitwise_or(
                cv2.inRange(hsv, hsv_lower1, hsv_upper1),
                cv2.inRange(hsv, hsv_lower2, hsv_upper2)
            )
        mask = cv2.bitwise_and(mask, hsv_mask)

    return mask