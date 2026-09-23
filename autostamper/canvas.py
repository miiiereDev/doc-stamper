from pathlib import Path

import fitz
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush
from PySide6.QtWidgets import QWidget

from .config import StampConfig


HANDLE_SIZE = 8


class PDFCanvasWidget(QWidget):
    config_changed = Signal(object)

    def __init__(self, config: StampConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._pixmap: QPixmap | None = None
        self._stamp_pixmap: QPixmap | None = None
        self._page_w: float = 612.0
        self._page_h: float = 792.0
        self._pdf_path: Path | None = None
        self._offset_x = 0
        self._offset_y = 0
        self._draw_w = 0
        self._draw_h = 0

        self._dragging = False
        self._resizing = False
        self._resize_dir: str | None = None
        self._drag_start = QPointF()
        self._orig_rect = QRectF()

        self.setMouseTracking(True)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background: #2b2b2b;")

    def set_stamp(self, png_path: Path | str | None):
        if not png_path:
            self._stamp_pixmap = None
            self.update()
            return
        p = Path(png_path)
        if not p.exists():
            self._stamp_pixmap = None
            self.update()
            return
        pm = QPixmap(str(p))
        if pm.isNull():
            self._stamp_pixmap = None
        else:
            self._stamp_pixmap = pm
        self.update()

    def set_config(self, config: StampConfig):
        self.config = config
        self.update()

    def load_pdf(self, pdf_path: Path, target_page: str = "last"):
        self._pdf_path = Path(pdf_path)
        if not self._pdf_path.exists():
            self._pixmap = None
            self.update()
            return False
        try:
            doc = fitz.open(str(self._pdf_path))
            if doc.is_encrypted:
                doc.close()
                self._pixmap = None
                self.update()
                return False
            idx = 0 if target_page == "first" else len(doc) - 1
            if idx < 0:
                idx = 0
            page = doc[idx]
            self._page_w = float(page.rect.width)
            self._page_h = float(page.rect.height)
            pix = page.get_pixmap(dpi=96)
            mode = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
            img = QImage(pix.samples, pix.w, pix.h, pix.stride, mode).copy()
            self._pixmap = QPixmap.fromImage(img)
            doc.close()
            del doc
            self.update()
            return True
        except Exception:
            self._pixmap = None
            self.update()
            return False

    def clear(self):
        self._pixmap = None
        self._pdf_path = None
        self.update()

    def _display_rect(self) -> QRectF:
        if not self._pixmap:
            return QRectF()
        return QRectF(self._offset_x, self._offset_y, self._draw_w, self._draw_h)

    def _stamp_rect(self) -> QRectF:
        d = self._display_rect()
        if d.isEmpty():
            return QRectF()
        return QRectF(
            d.x() + self.config.rel_x * d.width(),
            d.y() + self.config.rel_y * d.height(),
            self.config.rel_w * d.width(),
            self.config.rel_h * d.height(),
        )

    def _handle_rects(self) -> dict[str, QRectF]:
        r = self._stamp_rect()
        if r.isEmpty():
            return {}
        hs = HANDLE_SIZE
        cx = r.center().x()
        cy = r.center().y()
        return {
            "tl": QRectF(r.left() - hs / 2, r.top() - hs / 2, hs, hs),
            "tr": QRectF(r.right() - hs / 2, r.top() - hs / 2, hs, hs),
            "bl": QRectF(r.left() - hs / 2, r.bottom() - hs / 2, hs, hs),
            "br": QRectF(r.right() - hs / 2, r.bottom() - hs / 2, hs, hs),
            "t": QRectF(cx - hs / 2, r.top() - hs / 2, hs, hs),
            "b": QRectF(cx - hs / 2, r.bottom() - hs / 2, hs, hs),
            "l": QRectF(r.left() - hs / 2, cy - hs / 2, hs, hs),
            "r": QRectF(r.right() - hs / 2, cy - hs / 2, hs, hs),
        }

    def _hit_test(self, pos: QPointF) -> str | None:
        for k, rect in self._handle_rects().items():
            if rect.contains(pos):
                return k
        if self._stamp_rect().contains(pos):
            return "move"
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self._pixmap:
            painter.setPen(QColor("#888"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No PDF loaded\nSelect input folder")
            return

        avail_w = self.width() - 20
        avail_h = self.height() - 20
        if avail_w <= 0 or avail_h <= 0:
            return
        pm_w = self._pixmap.width()
        pm_h = self._pixmap.height()
        scale = min(avail_w / pm_w, avail_h / pm_h)
        scale = min(scale, 2.0)
        self._draw_w = pm_w * scale
        self._draw_h = pm_h * scale
        self._offset_x = (self.width() - self._draw_w) / 2
        self._offset_y = (self.height() - self._draw_h) / 2

        target = QRectF(self._offset_x, self._offset_y, self._draw_w, self._draw_h)
        painter.drawPixmap(target.toRect(), self._pixmap)

        r = self._stamp_rect()
        if self._stamp_pixmap and not self._stamp_pixmap.isNull():
            painter.setOpacity(0.85)
            painter.drawPixmap(r.toRect(), self._stamp_pixmap)
            painter.setOpacity(1.0)
        else:
            painter.setBrush(QBrush(QColor(0, 191, 255, 40)))
            painter.drawRect(r)
            painter.setBrush(QBrush(Qt.NoBrush))
        painter.setPen(QPen(QColor("#00BFFF"), 2, Qt.DashLine))
        painter.setBrush(QBrush(Qt.NoBrush))
        painter.drawRect(r)

        painter.setPen(QPen(QColor("#00BFFF"), 1))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        for rect in self._handle_rects().values():
            painter.drawRect(rect)

        painter.setPen(QColor("#FFF"))
        painter.drawText(
            int(r.left()), int(max(12, r.top() - 4)),
            f"{self._page_w:.0f} x {self._page_h:.0f} pt"
        )

    def mousePressEvent(self, event):
        if not self._pixmap or event.button() != Qt.LeftButton:
            return
        pos = QPointF(event.position())
        hit = self._hit_test(pos)
        if not hit:
            return
        if hit == "move":
            self._dragging = True
            self._drag_start = pos
            self._orig_rect = self._stamp_rect()
        else:
            self._resizing = True
            self._resize_dir = hit
            self._drag_start = pos
            self._orig_rect = self._stamp_rect()

    def mouseMoveEvent(self, event):
        if not self._pixmap:
            return
        pos = QPointF(event.position())
        if not self._dragging and not self._resizing:
            hit = self._hit_test(pos)
            if hit in ("tl", "br"):
                self.setCursor(Qt.SizeFDiagCursor)
            elif hit in ("tr", "bl"):
                self.setCursor(Qt.SizeBDiagCursor)
            elif hit in ("t", "b"):
                self.setCursor(Qt.SizeVerCursor)
            elif hit in ("l", "r"):
                self.setCursor(Qt.SizeHorCursor)
            elif hit == "move":
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            return

        d = self._display_rect()
        if d.isEmpty():
            return
        dx = pos.x() - self._drag_start.x()
        dy = pos.y() - self._drag_start.y()

        if self._dragging:
            new_x = self._orig_rect.x() + dx
            new_y = self._orig_rect.y() + dy
            new_x = max(d.left(), min(new_x, d.right() - self._orig_rect.width()))
            new_y = max(d.top(), min(new_y, d.bottom() - self._orig_rect.height()))
            self.config.rel_x = (new_x - d.x()) / d.width()
            self.config.rel_y = (new_y - d.y()) / d.height()
            self.update()
            self.config_changed.emit(self.config)
            return

        if self._resizing:
            r = QRectF(self._orig_rect)
            if "l" in self._resize_dir:
                r.setLeft(min(r.right() - 12, r.left() + dx))
                r.setLeft(max(r.left(), d.left()))
            if "r" in self._resize_dir:
                r.setRight(max(r.left() + 12, r.right() + dx))
                r.setRight(min(r.right(), d.right()))
            if "t" in self._resize_dir:
                r.setTop(min(r.bottom() - 12, r.top() + dy))
                r.setTop(max(r.top(), d.top()))
            if "b" in self._resize_dir:
                r.setBottom(max(r.top() + 12, r.bottom() + dy))
                r.setBottom(min(r.bottom(), d.bottom()))

            if self.config.keep_aspect:
                aspect = None
                if self._stamp_pixmap and not self._stamp_pixmap.isNull():
                    aspect = self._stamp_pixmap.width() / max(1, self._stamp_pixmap.height())
                elif self._orig_rect.height() != 0:
                    aspect = self._orig_rect.width() / self._orig_rect.height()
                if aspect and aspect > 0:
                    w = r.width()
                    h = r.height()
                    dirc = self._resize_dir
                    if dirc in ("tl", "tr", "bl", "br"):
                        if w / max(1, h) > aspect:
                            new_w = h * aspect
                            if "l" in dirc:
                                r.setLeft(r.right() - new_w)
                            else:
                                r.setRight(r.left() + new_w)
                        else:
                            new_h = w / aspect
                            if "t" in dirc:
                                r.setTop(r.bottom() - new_h)
                            else:
                                r.setBottom(r.top() + new_h)
                    elif dirc in ("l", "r"):
                        new_h = w / aspect
                        cy = self._orig_rect.center().y()
                        r.setTop(cy - new_h / 2)
                        r.setBottom(cy + new_h / 2)
                        if r.top() < d.top():
                            r.moveTop(d.top())
                        if r.bottom() > d.bottom():
                            r.moveBottom(d.bottom())
                        if r.height() != new_h:
                            adj_w = r.height() * aspect
                            if dirc == "l":
                                r.setLeft(r.right() - adj_w)
                            else:
                                r.setRight(r.left() + adj_w)
                    elif dirc in ("t", "b"):
                        new_w = h * aspect
                        cx = self._orig_rect.center().x()
                        r.setLeft(cx - new_w / 2)
                        r.setRight(cx + new_w / 2)
                        if r.left() < d.left():
                            r.moveLeft(d.left())
                        if r.right() > d.right():
                            r.moveRight(d.right())
                        if r.width() != new_w:
                            adj_h = r.width() / aspect
                            if dirc == "t":
                                r.setTop(r.bottom() - adj_h)
                            else:
                                r.setBottom(r.top() + adj_h)

            self.config.rel_x = (r.x() - d.x()) / d.width()
            self.config.rel_y = (r.y() - d.y()) / d.height()
            self.config.rel_w = r.width() / d.width()
            self.config.rel_h = r.height() / d.height()
            self.config.rel_w = max(0.02, min(0.98, self.config.rel_w))
            self.config.rel_h = max(0.02, min(0.98, self.config.rel_h))
            self.update()
            self.config_changed.emit(self.config)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._resizing = False
        self._resize_dir = None
        self.setCursor(Qt.ArrowCursor)
