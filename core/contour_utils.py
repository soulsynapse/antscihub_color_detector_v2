# core/contour_utils.py
import cv2
import numpy as np


def merge_contours(contours, merge_dist):
    """Merge contours whose bounding box centers are within merge_dist pixels."""
    if merge_dist <= 0 or len(contours) <= 1:
        return contours

    bboxes = [cv2.boundingRect(c) for c in contours]
    n = len(contours)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        xi, yi, wi, hi = bboxes[i]
        ci_x = xi + wi / 2
        ci_y = yi + hi / 2
        for j in range(i + 1, n):
            xj, yj, wj, hj = bboxes[j]
            cj_x = xj + wj / 2
            cj_y = yj + hj / 2
            dist = np.sqrt((ci_x - cj_x) ** 2 + (ci_y - cj_y) ** 2)
            if dist < merge_dist:
                union(i, j)

    groups = {}
    for i in range(n):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(contours[i])

    merged = []
    for group in groups.values():
        merged.append(np.vstack(group))

    return merged


def find_valid_contours(mask, min_area, merge_distance=0):
    """Find contours, filter by area, optionally merge nearby ones."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid = [c for c in contours if cv2.contourArea(c) > min_area]

    if merge_distance > 0 and len(valid) > 1:
        valid = merge_contours(valid, merge_distance)
        valid = [c for c in valid if cv2.contourArea(c) > min_area]

    return valid