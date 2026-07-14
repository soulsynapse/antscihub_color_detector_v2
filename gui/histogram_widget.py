# gui/histogram_widget.py (COMPLETE UPDATED VERSION)
import numpy as np
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import (QPainter, QColor, QPen, QBrush, QFont, QMouseEvent,
                          QKeyEvent)
from core.color_store import ColorStore


class HistogramWidget(QWidget):
    MARGIN_LEFT = 30
    MARGIN_RIGHT = 10
    MARGIN_TOP = 20
    MARGIN_BOTTOM = 20
    BAR_HIT_ZONE = 8

    def __init__(self, x_name: str, y_name: str,
                 x_range: tuple, y_range: tuple,
                 color_store: ColorStore):
        super().__init__()
        self.x_name = x_name
        self.y_name = y_name
        self.x_range = x_range
        self.y_range = y_range
        self.color_store = color_store

        self.color_points = []
        self.show_masked = False  # toggled by shift

        bounds = self.color_store.get_bounds()
        self.x_lo = bounds[x_name][0]
        self.x_hi = bounds[x_name][1]
        self.y_lo = bounds[y_name][0]
        self.y_hi = bounds[y_name][1]

        self._dragging = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(180, 140)

    def _plot_rect(self) -> QRect:
        return QRect(
            self.MARGIN_LEFT, self.MARGIN_TOP,
            max(1, self.width() - self.MARGIN_LEFT - self.MARGIN_RIGHT),
            max(1, self.height() - self.MARGIN_TOP - self.MARGIN_BOTTOM)
        )

    def _data_to_pixel_x(self, val):
        r = self._plot_rect()
        denom = self.x_range[1] - self.x_range[0]
        if denom == 0:
            denom = 1
        frac = (val - self.x_range[0]) / denom
        return r.left() + frac * r.width()

    def _data_to_pixel_y(self, val):
        r = self._plot_rect()
        denom = self.y_range[1] - self.y_range[0]
        if denom == 0:
            denom = 1
        frac = (val - self.y_range[0]) / denom
        return r.bottom() - frac * r.height()

    def _pixel_to_data_x(self, px):
        r = self._plot_rect()
        w = r.width()
        if w == 0:
            w = 1
        frac = (px - r.left()) / w
        frac = float(np.clip(frac, 0, 1))
        return int(round(self.x_range[0] + frac * (self.x_range[1] - self.x_range[0])))

    def _pixel_to_data_y(self, py):
        r = self._plot_rect()
        h = r.height()
        if h == 0:
            h = 1
        frac = (r.bottom() - py) / h
        frac = float(np.clip(frac, 0, 1))
        return int(round(self.y_range[0] + frac * (self.y_range[1] - self.y_range[0])))

    def set_color_points(self, colors: list):
        self.color_points = colors
        bounds = self.color_store.get_bounds()
        self.x_lo = bounds[self.x_name][0]
        self.x_hi = bounds[self.x_name][1]
        self.y_lo = bounds[self.y_name][0]
        self.y_hi = bounds[self.y_name][1]

    def _bgr_to_qcolor(self, bgr):
        return QColor(int(bgr[2]), int(bgr[1]), int(bgr[0]))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Dark neutral background
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        r = self._plot_rect()
        if r.width() <= 0 or r.height() <= 0:
            painter.end()
            return

        # Plot area - pure black
        painter.fillRect(r, QColor(0, 0, 0))

        x_lo_px = self._data_to_pixel_x(self.x_lo)
        x_hi_px = self._data_to_pixel_x(self.x_hi)
        y_lo_px = self._data_to_pixel_y(self.y_lo)
        y_hi_px = self._data_to_pixel_y(self.y_hi)

        sel_left = int(min(x_lo_px, x_hi_px))
        sel_right = int(max(x_lo_px, x_hi_px))
        sel_top = int(min(y_lo_px, y_hi_px))
        sel_bottom = int(max(y_lo_px, y_hi_px))

        # Selected region - very subtle light tint
        sel_rect = QRect(sel_left, sel_top, sel_right - sel_left, sel_bottom - sel_top)
        painter.fillRect(sel_rect, QColor(255, 255, 255, 15))

        # Dim outside regions
        painter.fillRect(QRect(r.left(), r.top(), sel_left - r.left(), r.height()),
                         QColor(0, 0, 0, 120))
        painter.fillRect(QRect(sel_right, r.top(), r.right() - sel_right, r.height()),
                         QColor(0, 0, 0, 120))
        painter.fillRect(QRect(sel_left, r.top(), sel_right - sel_left, sel_top - r.top()),
                         QColor(0, 0, 0, 120))
        painter.fillRect(QRect(sel_left, sel_bottom, sel_right - sel_left, r.bottom() - sel_bottom),
                         QColor(0, 0, 0, 120))

        # Boundary lines - white so they're neutral
        pen = QPen(QColor(255, 255, 255, 160), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(int(x_lo_px), r.top(), int(x_lo_px), r.bottom())
        painter.drawLine(int(x_hi_px), r.top(), int(x_hi_px), r.bottom())
        painter.drawLine(r.left(), int(y_lo_px), r.right(), int(y_lo_px))
        painter.drawLine(r.left(), int(y_hi_px), r.right(), int(y_hi_px))

        # Draw color points
        if self.color_points:
            for cp in self.color_points:
                in_bounds = self.color_store.is_color_in_bounds(cp)

                # In masked mode, skip out-of-bounds points entirely
                if self.show_masked and not in_bounds:
                    continue

                xv = cp[self.x_name]
                yv = cp[self.y_name]
                px = int(self._data_to_pixel_x(xv))
                py = int(self._data_to_pixel_y(yv))

                if not r.contains(QPoint(px, py)):
                    continue

                fill_color = self._bgr_to_qcolor(cp['BGR'])

                # Thin white outline for visibility on dark background
                painter.setPen(QPen(QColor(255, 255, 255, 100), 0.5))
                painter.setBrush(QBrush(fill_color))
                painter.drawEllipse(QPoint(px, py), 3, 3)

        # Border
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)

        # Title
        painter.setPen(QColor(200, 200, 200))
        font = QFont("Monospace", 8)
        painter.setFont(font)
        title = f"{self.x_name} vs {self.y_name}"
        if self.show_masked:
            title += "  [MASKED]"
        painter.drawText(r.left(), r.top() - 5, title)

        # Axis labels
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(r.left() - 2, r.bottom() + 14, str(self.x_range[0]))
        x_end_text = str(self.x_range[1])
        painter.drawText(r.right() - len(x_end_text) * 6, r.bottom() + 14, x_end_text)
        painter.drawText(2, r.bottom() + 4, str(self.y_range[0]))
        painter.drawText(2, r.top() + 10, str(self.y_range[1]))

        # Bound values
        font_small = QFont("Monospace", 7)
        painter.setFont(font_small)
        painter.setPen(QColor(255, 255, 255, 200))
        painter.drawText(int(x_lo_px) + 3, r.bottom() + 13, str(self.x_lo))
        painter.drawText(int(x_hi_px) - 20, r.bottom() + 13, str(self.x_hi))
        painter.drawText(r.right() + 2, int(y_lo_px) + 4, str(self.y_lo))
        painter.drawText(r.right() + 2, int(y_hi_px) + 4, str(self.y_hi))

        # Point count
        if self.color_points:
            in_count = sum(1 for cp in self.color_points
                          if self.color_store.is_color_in_bounds(cp))
            total = len(self.color_points)
            painter.setPen(QColor(180, 180, 180))
            painter.setFont(QFont("Monospace", 7))
            painter.drawText(r.right() - 60, r.top() - 5, f"{in_count}/{total}")

        painter.end()

    def _hit_test(self, pos) -> str | None:
        r = self._plot_rect()
        px, py = pos.x(), pos.y()

        x_lo_px = self._data_to_pixel_x(self.x_lo)
        x_hi_px = self._data_to_pixel_x(self.x_hi)
        y_lo_px = self._data_to_pixel_y(self.y_lo)
        y_hi_px = self._data_to_pixel_y(self.y_hi)

        hz = self.BAR_HIT_ZONE

        if r.top() - hz <= py <= r.bottom() + hz:
            if abs(px - x_lo_px) < hz:
                return 'x_lo'
            if abs(px - x_hi_px) < hz:
                return 'x_hi'

        if r.left() - hz <= px <= r.right() + hz:
            if abs(py - y_lo_px) < hz:
                return 'y_lo'
            if abs(py - y_hi_px) < hz:
                return 'y_hi'

        return None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test(event.pos())
            if hit:
                self._dragging = hit

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            if self._dragging in ('x_lo', 'x_hi'):
                val = self._pixel_to_data_x(event.pos().x())
                val = max(self.x_range[0], min(self.x_range[1], val))
                if self._dragging == 'x_lo':
                    self.x_lo = min(val, self.x_hi)
                else:
                    self.x_hi = max(val, self.x_lo)
            else:
                val = self._pixel_to_data_y(event.pos().y())
                val = max(self.y_range[0], min(self.y_range[1], val))
                if self._dragging == 'y_lo':
                    self.y_lo = min(val, self.y_hi)
                else:
                    self.y_hi = max(val, self.y_lo)
            self._sync_bounds_to_store()
            self.update()
        else:
            hit = self._hit_test(event.pos())
            if hit in ('x_lo', 'x_hi'):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif hit in ('y_lo', 'y_hi'):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = None
            self._sync_bounds_to_store()

    def _sync_bounds_to_store(self):
        self.color_store.set_bound(self.x_name, self.x_lo, self.x_hi)
        self.color_store.set_bound(self.y_name, self.y_lo, self.y_hi)