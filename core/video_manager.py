# core/video_manager.py
import cv2
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal


class VideoManager(QObject):
    """
    Manages video loading, seeking, and frame retrieval.
    Decoupled from GUI so it can be reused.
    """
    frame_changed = pyqtSignal(np.ndarray)
    video_loaded = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.cap = None
        self.video_path = None
        self.total_frames = 0
        self.current_frame_idx = 0
        self.fps = 30.0
        self.width = 0
        self.height = 0
        self._current_frame = None

    def load_video(self, path: str) -> bool:
        if self.cap is not None:
            self.cap.release()

        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            self.cap = None
            return False

        self.video_path = path
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0:
            self.fps = 30.0
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.current_frame_idx = 0

        self.video_loaded.emit()
        return True

    def is_loaded(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def seek(self, frame_idx: int):
        if not self.is_loaded():
            return
        frame_idx = max(0, min(frame_idx, self.total_frames - 1))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        self.current_frame_idx = frame_idx
        ret, frame = self.cap.read()
        if ret:
            self._current_frame = frame

    def get_current_frame(self) -> np.ndarray | None:
        return self._current_frame

    def get_frame_at(self, frame_idx: int) -> np.ndarray | None:
        if not self.is_loaded():
            return None
        old_pos = self.current_frame_idx
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self.cap.read()
        # Restore position
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, old_pos)
        return frame if ret else None

    def get_time_str(self, frame_idx: int = None) -> str:
        if frame_idx is None:
            frame_idx = self.current_frame_idx
        total_seconds = frame_idx / self.fps
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:05.2f}"

    def release(self):
        if self.cap:
            self.cap.release()
            self.cap = None

    def __del__(self):
        self.release()