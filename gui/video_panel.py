# gui/video_panel.py
import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint, QRect, QThread
from PyQt6.QtGui import QImage, QPixmap, QMouseEvent, QCursor, QPainter, QPen, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSlider,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyleOptionSlider,
    QStyle,
)

from core.color_store import ColorStore
from core.video_manager import VideoManager
from core.mask_builder import build_mask
from core.contour_utils import find_valid_contours


class ClickableLabel(QLabel):
    clicked = pyqtSignal(QPoint)

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 240)
        self.setStyleSheet("background-color: #1a1a1a; border: 1px solid #333;")
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setMouseTracking(True)
        self._pixmap = None
        self._crop_origin = QPoint(0, 0)
        self._source_rect = QRect()
        self._display_rect = QRect()
        self._overview_rect = QRect()
        self._overview_view_rect = QRect()
        self._dragging_overview = False
        self._center_crop_on_next_display = True

    def setFramePixmap(self, pixmap: QPixmap):
        if self._pixmap is None or self._pixmap.size() != pixmap.size():
            self._center_crop_on_next_display = True
        self._pixmap = pixmap
        self.setText("")
        self._update_display()

    def setScaledPixmap(self, pixmap: QPixmap):
        self.setFramePixmap(pixmap)

    def reset_crop(self):
        self._center_crop_on_next_display = True
        if self._pixmap:
            self._update_display()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap:
            self._update_display()

    def paintEvent(self, event):
        if not self._pixmap:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))

        if not self._source_rect.isEmpty() and not self._display_rect.isEmpty():
            painter.drawPixmap(self._display_rect, self._pixmap, self._source_rect)

        if not self._overview_rect.isEmpty():
            full_source = QRect(0, 0, self._pixmap.width(), self._pixmap.height())
            painter.fillRect(self._overview_rect.adjusted(-2, -2, 2, 2), QColor(12, 12, 12, 210))
            painter.drawPixmap(self._overview_rect, self._pixmap, full_source)
            painter.setPen(QPen(QColor(0, 0, 0, 220), 3))
            painter.drawRect(self._overview_view_rect)
            painter.fillRect(self._overview_view_rect, QColor(90, 210, 255, 45))
            painter.setPen(QPen(QColor(110, 230, 255), 2))
            painter.drawRect(self._overview_view_rect)
            painter.setPen(QPen(QColor("#dddddd"), 1))
            painter.drawRect(self._overview_rect.adjusted(-1, -1, 1, 1))

        painter.setPen(QPen(QColor("#333333"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()

    def _update_display(self):
        if not self._pixmap:
            return

        content = self.rect().adjusted(1, 1, -1, -1)
        if content.width() <= 0 or content.height() <= 0:
            return

        display_w = min(self._pixmap.width(), content.width())
        display_h = min(self._pixmap.height(), content.height())
        if self._center_crop_on_next_display:
            self._crop_origin = QPoint(
                max(0, (self._pixmap.width() - display_w) // 2),
                max(0, (self._pixmap.height() - display_h) // 2),
            )
            self._center_crop_on_next_display = False
        else:
            self._crop_origin = self._clamped_crop_origin(self._crop_origin, display_w, display_h)

        self._source_rect = QRect(
            self._crop_origin.x(),
            self._crop_origin.y(),
            display_w,
            display_h,
        )
        self._display_rect = QRect(
            content.x() + (content.width() - display_w) // 2,
            content.y() + (content.height() - display_h) // 2,
            display_w,
            display_h,
        )
        self._update_overview_rects()
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton or not self._pixmap:
            return super().mousePressEvent(event)

        pos = event.pos()
        if self._overview_rect.contains(pos):
            self._dragging_overview = True
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
            self._set_crop_center_from_overview(pos)
            return

        if self._display_rect.contains(pos):
            orig_x = self._source_rect.x() + pos.x() - self._display_rect.x()
            orig_y = self._source_rect.y() + pos.y() - self._display_rect.y()
            self.clicked.emit(QPoint(orig_x, orig_y))

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging_overview:
            self._set_crop_center_from_overview(event.pos())
            return
        self._update_cursor(event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_overview:
            self._dragging_overview = False
            self._update_cursor(event.pos())
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if not self._dragging_overview:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        super().leaveEvent(event)

    def _clamped_crop_origin(self, origin: QPoint, display_w: int, display_h: int) -> QPoint:
        max_x = max(0, self._pixmap.width() - display_w)
        max_y = max(0, self._pixmap.height() - display_h)
        x = max(0, min(origin.x(), max_x))
        y = max(0, min(origin.y(), max_y))
        return QPoint(x, y)

    def _set_crop_center_from_overview(self, pos: QPoint):
        if self._overview_rect.isEmpty() or self._source_rect.isEmpty():
            return

        rel_x = max(0, min(pos.x() - self._overview_rect.x(), self._overview_rect.width()))
        rel_y = max(0, min(pos.y() - self._overview_rect.y(), self._overview_rect.height()))
        center_x = int(rel_x * self._pixmap.width() / max(1, self._overview_rect.width()))
        center_y = int(rel_y * self._pixmap.height() / max(1, self._overview_rect.height()))

        origin = QPoint(
            center_x - self._source_rect.width() // 2,
            center_y - self._source_rect.height() // 2,
        )
        self._crop_origin = self._clamped_crop_origin(
            origin,
            self._source_rect.width(),
            self._source_rect.height(),
        )
        self._update_display()

    def _update_cursor(self, pos: QPoint):
        if self._pixmap and self._overview_rect.contains(pos):
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def _update_overview_rects(self):
        needs_crop = (
            self._pixmap.width() > self._source_rect.width()
            or self._pixmap.height() > self._source_rect.height()
        )
        if not needs_crop:
            self._overview_rect = QRect()
            self._overview_view_rect = QRect()
            return

        max_overview_w = min(180, max(90, self.width() // 4))
        max_overview_h = min(130, max(70, self.height() // 4))
        scale = min(
            max_overview_w / self._pixmap.width(),
            max_overview_h / self._pixmap.height(),
        )
        overview_w = max(1, int(self._pixmap.width() * scale))
        overview_h = max(1, int(self._pixmap.height() * scale))
        self._overview_rect = QRect(10, 10, overview_w, overview_h)

        view_x = self._overview_rect.x() + int(self._source_rect.x() * scale)
        view_y = self._overview_rect.y() + int(self._source_rect.y() * scale)
        view_w = max(6, int(self._source_rect.width() * scale))
        view_h = max(6, int(self._source_rect.height() * scale))
        view_w = min(view_w, self._overview_rect.right() - view_x + 1)
        view_h = min(view_h, self._overview_rect.bottom() - view_y + 1)
        self._overview_view_rect = QRect(view_x, view_y, view_w, view_h)


class DetectionMarkerSlider(QSlider):
    """Scrubber that can draw frame markers for 0 detections and 2+ detections."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._zero_frames = []
        self._two_plus_frames = []
        self._show_zero = False
        self._show_two_plus = False

    def set_marker_frames(self, zero_frames, two_plus_frames):
        self._zero_frames = list(zero_frames)
        self._two_plus_frames = list(two_plus_frames)
        self.update()

    def set_marker_visibility(self, show_zero: bool, show_two_plus: bool):
        self._show_zero = bool(show_zero)
        self._show_two_plus = bool(show_two_plus)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.maximum() <= 0:
            return
        if not (self._show_zero or self._show_two_plus):
            return

        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )

        if not groove.isValid() or groove.width() <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        if self._show_zero:
            self._draw_markers(painter, groove, self._zero_frames, QColor(255, 90, 90, 180))

        if self._show_two_plus:
            self._draw_markers(painter, groove, self._two_plus_frames, QColor(255, 205, 70, 180))

        painter.end()

    def _draw_markers(self, painter: QPainter, groove, frames, color: QColor):
        if not frames:
            return

        left = groove.left()
        width = max(1, groove.width())
        max_frame = max(1, self.maximum())

        xs = set()
        for frame_idx in frames:
            if frame_idx < 0 or frame_idx > max_frame:
                continue
            x = left + int(round((frame_idx / max_frame) * width))
            x = max(left, min(groove.right(), x))
            xs.add(x)

        y1 = max(0, groove.top() - 3)
        y2 = min(self.height() - 1, groove.bottom() + 3)

        painter.setPen(QPen(color, 1))
        for x in xs:
            painter.drawLine(x, y1, x, y2)


class MarkerScanWorker(QThread):
    finished = pyqtSignal(object, list, list)
    failed = pyqtSignal(str)

    def __init__(self, video_path, bounds, default_bounds, min_area, merge_distance, cache_key):
        super().__init__()
        self.video_path = video_path
        self.bounds = bounds
        self.default_bounds = default_bounds
        self.min_area = min_area
        self.merge_distance = merge_distance
        self.cache_key = cache_key
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            self.failed.emit("Could not open video for marker scan.")
            return

        zero_frames = []
        two_plus_frames = []
        frame_idx = 0

        while True:
            if self._cancelled:
                cap.release()
                return

            ret, frame = cap.read()
            if not ret:
                break

            mask = build_mask(frame, self.bounds, self.default_bounds)
            valid = find_valid_contours(mask, self.min_area, self.merge_distance)
            count = len(valid)

            if count == 0:
                zero_frames.append(frame_idx)
            if count >= 2:
                two_plus_frames.append(frame_idx)

            frame_idx += 1

        cap.release()
        if self._cancelled:
            return

        self.finished.emit(self.cache_key, zero_frames, two_plus_frames)


class VideoPanel(QWidget):
    def __init__(self, video_manager: VideoManager, color_store: ColorStore):
        super().__init__()
        self.video_manager = video_manager
        self.color_store = color_store
        self.show_mask = False
        self.current_frame_bgr = None

        self._shift_mask = False
        self._was_mask_off = False

        self._marker_worker = None
        self._marker_cache_key = None
        self._zero_marker_frames = []
        self._two_plus_marker_frames = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        self.video_label = ClickableLabel()
        self.video_label.setText("Open a video file (File -> Open Video)")
        self.video_label.clicked.connect(self._on_click)
        layout.addWidget(self.video_label, 1)

        self.color_info_label = QLabel("Click on video to pick 11x11 color region")
        self.color_info_label.setStyleSheet(
            "color: #aaa; background: #222; padding: 3px; "
            "font-family: monospace; font-size: 10px; border: 1px solid #333;"
        )
        self.color_info_label.setFixedHeight(22)
        layout.addWidget(self.color_info_label)

        controls_layout = QVBoxLayout()

        scrubber_layout = QHBoxLayout()
        self.time_label_left = QLabel("00:00.00")
        self.time_label_left.setStyleSheet("color: #aaa; font-family: monospace; font-size: 10px;")
        self.time_label_left.setFixedWidth(60)
        scrubber_layout.addWidget(self.time_label_left)

        self.scrubber = DetectionMarkerSlider(Qt.Orientation.Horizontal)
        self.scrubber.setMinimum(0)
        self.scrubber.setMaximum(0)
        self.scrubber.valueChanged.connect(self._on_scrub)
        self.scrubber.setStyleSheet(
            "QSlider::groove:horizontal { background: #333; height: 8px; border-radius: 4px; }"
            "QSlider::handle:horizontal { background: #aaa; width: 14px; margin: -4px 0; border-radius: 7px; }"
            "QSlider::sub-page:horizontal { background: #4a8a4a; border-radius: 4px; }"
        )
        scrubber_layout.addWidget(self.scrubber)

        self.time_label_right = QLabel("00:00.00")
        self.time_label_right.setStyleSheet("color: #aaa; font-family: monospace; font-size: 10px;")
        self.time_label_right.setFixedWidth(60)
        scrubber_layout.addWidget(self.time_label_right)

        controls_layout.addLayout(scrubber_layout)

        marker_layout = QHBoxLayout()
        marker_label = QLabel("Seeker markers:")
        marker_label.setStyleSheet("color: #888; font-size: 10px;")
        marker_layout.addWidget(marker_label)

        marker_btn_style = (
            "QPushButton { background: #2a2a2a; color: #aaa; border: 1px solid #555; "
            "padding: 3px 8px; border-radius: 3px; font-size: 10px; }"
            "QPushButton:hover { background: #3a3a3a; }"
            "QPushButton:checked { background: #2f3d2f; color: #c5ffc5; border: 1px solid #5a8a5a; }"
        )

        self.zero_markers_btn = QPushButton("0 detections")
        self.zero_markers_btn.setCheckable(True)
        self.zero_markers_btn.setStyleSheet(marker_btn_style)
        self.zero_markers_btn.toggled.connect(self._on_marker_toggle_changed)
        marker_layout.addWidget(self.zero_markers_btn)

        self.two_plus_markers_btn = QPushButton("2+ detections")
        self.two_plus_markers_btn.setCheckable(True)
        self.two_plus_markers_btn.setStyleSheet(marker_btn_style)
        self.two_plus_markers_btn.toggled.connect(self._on_marker_toggle_changed)
        marker_layout.addWidget(self.two_plus_markers_btn)

        marker_layout.addStretch()

        self.marker_status_label = QLabel("")
        self.marker_status_label.setStyleSheet("color: #777; font-family: monospace; font-size: 10px;")
        marker_layout.addWidget(self.marker_status_label)

        controls_layout.addLayout(marker_layout)

        btn_layout = QHBoxLayout()

        self.step_back_btn = QPushButton("<<")
        self.step_back_btn.setFixedWidth(36)
        self.step_back_btn.setToolTip("Step back 1 frame")
        self.step_back_btn.clicked.connect(self._step_back)
        btn_layout.addWidget(self.step_back_btn)

        self.play_btn = QPushButton("Play")
        self.play_btn.setFixedWidth(80)
        self.play_btn.clicked.connect(self.toggle_playback)
        btn_layout.addWidget(self.play_btn)

        self.step_fwd_btn = QPushButton(">>")
        self.step_fwd_btn.setFixedWidth(36)
        self.step_fwd_btn.setToolTip("Step forward 1 frame")
        self.step_fwd_btn.clicked.connect(self._step_forward)
        btn_layout.addWidget(self.step_fwd_btn)

        self.frame_label = QLabel("Frame: 0 / 0")
        self.frame_label.setStyleSheet("color: #aaa; font-family: monospace;")
        btn_layout.addWidget(self.frame_label)

        btn_layout.addStretch()

        self.mask_btn = QPushButton("Show Mask")
        self.mask_btn.setCheckable(True)
        self.mask_btn.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #aaa; border: 1px solid #555; "
            "padding: 4px 10px; border-radius: 3px; }"
            "QPushButton:checked { background: #2a4a2a; color: #aaffaa; border: 1px solid #4a8a4a; }"
            "QPushButton:hover { background: #3a3a3a; }"
        )
        self.mask_btn.toggled.connect(self._toggle_mask)
        btn_layout.addWidget(self.mask_btn)

        controls_layout.addLayout(btn_layout)
        layout.addLayout(controls_layout)

        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self._play_next_frame)
        self.is_playing = False

        self._marker_recompute_timer = QTimer(self)
        self._marker_recompute_timer.setSingleShot(True)
        self._marker_recompute_timer.timeout.connect(self._refresh_markers_if_visible)

    def on_video_loaded(self):
        total = self.video_manager.total_frames
        self.scrubber.setMaximum(max(0, total - 1))
        self.scrubber.setValue(0)
        self.video_label.reset_crop()
        self.video_manager.seek(0)
        frame = self.video_manager.get_current_frame()
        if frame is not None:
            self.current_frame_bgr = frame
            self._display_current_frame()
        self._update_frame_label()
        self.time_label_right.setText(self.video_manager.get_time_str(max(0, total - 1)))
        self.invalidate_detection_markers()

    def _on_scrub(self, value):
        if not self.video_manager.is_loaded():
            return
        self.video_manager.seek(value)
        frame = self.video_manager.get_current_frame()
        if frame is not None:
            self.current_frame_bgr = frame
            self._display_current_frame()
        self._update_frame_label()

    def toggle_playback(self):
        if not self.video_manager.is_loaded():
            return
        if self.is_playing:
            self.play_timer.stop()
            self.is_playing = False
            self.play_btn.setText("Play")
        else:
            fps = self.video_manager.fps
            interval = max(1, int(1000 / fps))
            self.play_timer.start(interval)
            self.is_playing = True
            self.play_btn.setText("Pause")

    def _play_next_frame(self):
        current = self.video_manager.current_frame_idx
        if current >= self.video_manager.total_frames - 1:
            self.toggle_playback()
            return
        next_frame = current + 1
        self.scrubber.blockSignals(True)
        self.scrubber.setValue(next_frame)
        self.scrubber.blockSignals(False)
        self.video_manager.seek(next_frame)
        frame = self.video_manager.get_current_frame()
        if frame is not None:
            self.current_frame_bgr = frame
            self._display_current_frame()
        self._update_frame_label()

    def _step_back(self):
        if not self.video_manager.is_loaded():
            return
        current = self.video_manager.current_frame_idx
        if current > 0:
            self.scrubber.setValue(current - 1)

    def _step_forward(self):
        if not self.video_manager.is_loaded():
            return
        current = self.video_manager.current_frame_idx
        if current < self.video_manager.total_frames - 1:
            self.scrubber.setValue(current + 1)

    def _toggle_mask(self, checked):
        self.show_mask = checked
        self.mask_btn.setText("Show Original" if checked else "Show Mask")
        self._display_current_frame()

    def display_frame(self, frame_bgr):
        self.current_frame_bgr = frame_bgr
        self._display_current_frame()

    def _display_current_frame(self):
        if self.current_frame_bgr is None:
            return

        if self.show_mask:
            display = self._apply_mask(self.current_frame_bgr)
        else:
            display = self.current_frame_bgr.copy()

        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimg)
        self.video_label.setFramePixmap(pixmap)

    def _apply_mask(self, frame_bgr):
        if not self.color_store.has_any_bounds():
            return frame_bgr.copy()

        bounds = self.color_store.get_bounds()
        mask = build_mask(frame_bgr, bounds, self.color_store.DEFAULT_BOUNDS)

        result = cv2.bitwise_and(frame_bgr, frame_bgr, mask=mask)
        bg = (frame_bgr * 0.2).astype(np.uint8)
        inv_mask = cv2.bitwise_not(mask)
        bg_part = cv2.bitwise_and(bg, bg, mask=inv_mask)
        result = cv2.add(result, bg_part)

        valid = find_valid_contours(mask, self.color_store.min_area, self.color_store.merge_distance)
        cv2.drawContours(result, valid, -1, (0, 255, 0), 1)

        return result

    def update_mask_overlay(self):
        if self.show_mask:
            self._display_current_frame()

    def _on_click(self, point: QPoint):
        if self.current_frame_bgr is None:
            return

        x, y = point.x(), point.y()
        h, w = self.current_frame_bgr.shape[:2]
        x = int(np.clip(x, 0, w - 1))
        y = int(np.clip(y, 0, h - 1))

        bgr = self.current_frame_bgr[y, x].copy()
        pixel_bgr = bgr.reshape(1, 1, 3)
        hsv = cv2.cvtColor(pixel_bgr, cv2.COLOR_BGR2HSV).flatten()
        ycrcb = cv2.cvtColor(pixel_bgr, cv2.COLOR_BGR2YCrCb).flatten()
        r, g, b = int(bgr[2]), int(bgr[1]), int(bgr[0])

        self.color_store.add_color_region(self.current_frame_bgr, x, y, radius=5)

        x_min = max(0, x - 5)
        x_max = min(w - 1, x + 5)
        y_min = max(0, y - 5)
        y_max = min(h - 1, y + 5)
        num_added = (x_max - x_min + 1) * (y_max - y_min + 1)

        self.color_info_label.setText(
            f"Picked 11x11 ({num_added}px) @ ({x},{y}) | "
            f"RGB({r},{g},{b}) | "
            f"H:{hsv[0]} S:{hsv[1]} V:{hsv[2]} | "
            f"Y:{ycrcb[0]} Cr:{ycrcb[1]} Cb:{ycrcb[2]}"
        )
        self.color_info_label.setStyleSheet(
            f"color: #fff; background: rgb({r},{g},{b}); padding: 3px; "
            "font-family: monospace; font-size: 10px; border: 1px solid #333;"
        )

    def _update_frame_label(self):
        if self.video_manager.is_loaded():
            idx = self.video_manager.current_frame_idx
            total = self.video_manager.total_frames
            self.frame_label.setText(f"Frame: {idx} / {total - 1}")
            self.time_label_left.setText(self.video_manager.get_time_str(idx))

    def set_shift_mask(self, masked: bool):
        self._shift_mask = masked
        if masked:
            if not self.show_mask:
                self._was_mask_off = True
                self.show_mask = True
                self.mask_btn.blockSignals(True)
                self.mask_btn.setChecked(True)
                self.mask_btn.setText("Show Original")
                self.mask_btn.blockSignals(False)
                self._display_current_frame()
        else:
            if self._was_mask_off:
                self._was_mask_off = False
                self.show_mask = False
                self.mask_btn.blockSignals(True)
                self.mask_btn.setChecked(False)
                self.mask_btn.setText("Show Mask")
                self.mask_btn.blockSignals(False)
                self._display_current_frame()

    def _on_marker_toggle_changed(self, _checked):
        show_zero = self.zero_markers_btn.isChecked()
        show_two_plus = self.two_plus_markers_btn.isChecked()

        self.scrubber.set_marker_visibility(show_zero, show_two_plus)
        if show_zero or show_two_plus:
            self._refresh_markers_if_visible()
        else:
            self.marker_status_label.setText("")

    def invalidate_detection_markers(self):
        self._marker_cache_key = None
        self._zero_marker_frames = []
        self._two_plus_marker_frames = []
        self.scrubber.set_marker_frames([], [])

        if self._marker_worker and self._marker_worker.isRunning():
            self._marker_worker.cancel()

        if self.zero_markers_btn.isChecked() or self.two_plus_markers_btn.isChecked():
            self.marker_status_label.setText("Markers updating...")
            self._marker_recompute_timer.start(300)
        else:
            self.marker_status_label.setText("")

    def _refresh_markers_if_visible(self):
        if not (self.zero_markers_btn.isChecked() or self.two_plus_markers_btn.isChecked()):
            return

        if not self.video_manager.is_loaded():
            self.marker_status_label.setText("Load a video to show markers")
            return

        cache_key = self._build_marker_cache_key()
        if self._marker_cache_key == cache_key:
            self.scrubber.set_marker_frames(self._zero_marker_frames, self._two_plus_marker_frames)
            self._update_marker_status_label()
            return

        if self._marker_worker and self._marker_worker.isRunning():
            self.marker_status_label.setText("Markers updating...")
            self._marker_recompute_timer.start(250)
            return

        self.marker_status_label.setText("Scanning detections for markers...")
        self._marker_worker = MarkerScanWorker(
            self.video_manager.video_path,
            self.color_store.get_bounds(),
            self.color_store.DEFAULT_BOUNDS,
            self.color_store.min_area,
            self.color_store.merge_distance,
            cache_key,
        )
        self._marker_worker.finished.connect(self._on_marker_scan_finished)
        self._marker_worker.failed.connect(self._on_marker_scan_failed)
        self._marker_worker.start()

    def _build_marker_cache_key(self):
        bounds = self.color_store.get_bounds()
        bounds_key = (
            ("H", int(bounds["H"][0]), int(bounds["H"][1])),
            ("S", int(bounds["S"][0]), int(bounds["S"][1])),
            ("V", int(bounds["V"][0]), int(bounds["V"][1])),
        )
        return (
            self.video_manager.video_path,
            int(self.video_manager.total_frames),
            bounds_key,
            int(self.color_store.min_area),
            int(self.color_store.merge_distance),
        )

    def _on_marker_scan_finished(self, cache_key, zero_frames, two_plus_frames):
        self._marker_worker = None

        current_key = self._build_marker_cache_key() if self.video_manager.is_loaded() else None
        if cache_key != current_key:
            if self.zero_markers_btn.isChecked() or self.two_plus_markers_btn.isChecked():
                self.marker_status_label.setText("Markers updating...")
                self._marker_recompute_timer.start(150)
            return

        self._marker_cache_key = cache_key
        self._zero_marker_frames = zero_frames
        self._two_plus_marker_frames = two_plus_frames

        self.scrubber.set_marker_frames(zero_frames, two_plus_frames)
        self._update_marker_status_label()

    def _on_marker_scan_failed(self, message):
        self._marker_worker = None
        self.marker_status_label.setText(message)

    def _update_marker_status_label(self):
        pieces = []
        if self.zero_markers_btn.isChecked():
            pieces.append(f"0: {len(self._zero_marker_frames)}")
        if self.two_plus_markers_btn.isChecked():
            pieces.append(f"2+: {len(self._two_plus_marker_frames)}")

        if pieces:
            self.marker_status_label.setText("Markers " + " | ".join(pieces))
        else:
            self.marker_status_label.setText("")
