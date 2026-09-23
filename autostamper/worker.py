import threading
from pathlib import Path

import fitz
from PySide6.QtCore import QThread, Signal

from .config import StampConfig


class StamperWorker(QThread):
    mismatch_detected = Signal(str, int, float, float)
    progress = Signal(int, int, str)
    file_status = Signal(str, str)
    error = Signal(str, str)
    finished = Signal()

    def __init__(self, pdf_paths: list[Path], stamp_path: Path, config: StampConfig,
                 pause_event: threading.Event, input_dir: Path, parent=None):
        super().__init__(parent)
        self.pdf_paths = [Path(p) for p in pdf_paths]
        self.stamp_path = Path(stamp_path)
        self.config = config
        self.pause_event = pause_event
        self.input_dir = Path(input_dir)
        self._action: str | None = None

    def set_action(self, action: str):
        self._action = action

    def resume_apply_once(self):
        self._action = "apply_once"
        self.pause_event.set()

    def resume_update_standard(self):
        self._action = "update_standard"
        self.pause_event.set()

    def resume_skip(self):
        self._action = "skip"
        self.pause_event.set()

    def run(self):
        total = len(self.pdf_paths)
        self.pause_event.set()

        out_dir = self.input_dir / ".stamped"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            self.error.emit(str(out_dir), f"Cannot create output dir: {e}")
            self.finished.emit()
            return

        if not self.stamp_path.exists():
            self.error.emit(str(self.stamp_path), "Stamp PNG not found")
            self.finished.emit()
            return

        for idx, pdf_path in enumerate(self.pdf_paths):
            pdf_path = Path(pdf_path)
            # already-done guard — per-file root vs .stamped comparison, never overwrite in Auto
            out_path = out_dir / pdf_path.name
            if out_path.exists():
                self.file_status.emit(str(pdf_path), "Skipped (Already Done)")
                self.progress.emit(idx + 1, total, pdf_path.name)
                continue
            try:
                doc = fitz.open(str(pdf_path))
            except Exception as e:
                self.file_status.emit(str(pdf_path), "Skipped (Corrupted)")
                self.error.emit(str(pdf_path), f"Open failed: {e}")
                self.progress.emit(idx + 1, total, pdf_path.name)
                continue

            if doc.is_encrypted:
                try:
                    doc.close()
                except Exception:
                    pass
                self.file_status.emit(str(pdf_path), "Skipped (Encrypted)")
                self.progress.emit(idx + 1, total, pdf_path.name)
                continue

            if len(doc) == 0:
                doc.close()
                self.file_status.emit(str(pdf_path), "Skipped (Empty)")
                self.progress.emit(idx + 1, total, pdf_path.name)
                continue

            page_idx = 0 if self.config.target_page == "first" else len(doc) - 1
            try:
                page = doc[page_idx]
                w = float(page.rect.width)
                h = float(page.rect.height)
            except Exception as e:
                doc.close()
                self.file_status.emit(str(pdf_path), "Skipped (Read Error)")
                self.error.emit(str(pdf_path), str(e))
                self.progress.emit(idx + 1, total, pdf_path.name)
                continue

            # halt on dimension tolerance OR aspect ratio change (1.5% default, regardless of lock, reuse halt UI)
            is_tolerance_mismatch = self.config.violates_tolerance(w, h)
            is_aspect_mismatch = self.config.violates_aspect(w, h)
            if is_tolerance_mismatch or is_aspect_mismatch:
                status = "Aspect Mismatch" if is_aspect_mismatch and not is_tolerance_mismatch else "Mismatch" if not is_aspect_mismatch else "Mismatch (Aspect+Size)"
                self.file_status.emit(str(pdf_path), status)
                self.mismatch_detected.emit(str(pdf_path), page_idx, w, h)
                self.pause_event.clear()
                self.pause_event.wait()
                if self._action == "skip":
                    try:
                        doc.close()
                    except Exception:
                        pass
                    self.file_status.emit(str(pdf_path), "Skipped")
                    self.progress.emit(idx + 1, total, pdf_path.name)
                    self._action = None
                    continue
                if self._action == "update_standard":
                    self.config.std_width = w
                    self.config.std_height = h
                    self._action = None

            rect = fitz.Rect(
                self.config.rel_x * w,
                self.config.rel_y * h,
                (self.config.rel_x + self.config.rel_w) * w,
                (self.config.rel_y + self.config.rel_h) * h,
            )

            try:
                page = doc[page_idx]
                if self.config.rotation % 360 != 0:
                    from .image import prepare_stamp_bytes
                    data = prepare_stamp_bytes(self.stamp_path, self.config.rotation)
                    if data:
                        pix = fitz.Pixmap(data)
                        page.insert_image(rect, pixmap=pix, keep_proportion=True, overlay=True)
                    else:
                        page.insert_image(rect, filename=str(self.stamp_path), keep_proportion=True)
                else:
                    page.insert_image(rect, filename=str(self.stamp_path), keep_proportion=self.config.keep_aspect)
            except Exception as e:
                try:
                    doc.close()
                except Exception:
                    pass
                self.file_status.emit(str(pdf_path), "Skipped (Stamp Error)")
                self.error.emit(str(pdf_path), f"insert_image failed: {e}")
                self.progress.emit(idx + 1, total, pdf_path.name)
                self._action = None
                continue

            out_path = out_dir / pdf_path.name
            try:
                doc.save(str(out_path), garbage=3, deflate=True)
            except Exception as e:
                self.file_status.emit(str(pdf_path), "Skipped (Save Error)")
                self.error.emit(str(pdf_path), f"save failed: {e}")
                try:
                    doc.close()
                except Exception:
                    pass
                self.progress.emit(idx + 1, total, pdf_path.name)
                self._action = None
                continue

            try:
                doc.close()
            except Exception:
                pass
            del doc

            self.file_status.emit(str(pdf_path), "Done")
            self.progress.emit(idx + 1, total, pdf_path.name)
            self._action = None

        self.finished.emit()
