import math
from pathlib import Path

import fitz
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush, QPolygonF, QTransform
from PySide6.QtWidgets import QWidget

from .config import StampConfig


HANDLE_SIZE = 8
ROTATION_HANDLE_OFFSET = 22
ROTATION_HANDLE_RADIUS = 7


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
        self._rotating = False
        self._resize_dir: str | None = None
        self._drag_start = QPointF()
        self._orig_rect = QRectF()
        self._rotate_start_angle = 0.0
        self._rotate_orig = 0.0

        self.setMouseTracking(True)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background: #2b2b2b;")

    # ---------- helpers ----------
    def _rotation_rad(self) -> float:
        return math.radians(self.config.rotation % 360)

    def _rotated_aabb_norm(self, rel_w=None, rel_h=None, rotation=None):
        rw = rel_w if rel_w is not None else self.config.rel_w
        rh = rel_h if rel_h is not None else self.config.rel_h
        rot = rotation if rotation is not None else self.config.rotation
        if rot % 360 == 0:
            return rw, rh
        rad = math.radians(rot % 360)
        c = abs(math.cos(rad))
        s = abs(math.sin(rad))
        w_px = rw * self._page_w
        h_px = rh * self._page_h
        w2 = w_px * c + h_px * s
        h2 = w_px * s + h_px * c
        return w2 / max(0.001, self._page_w), h2 / max(0.001, self._page_h)

    def _rotated_aabb_display(self, w: float, h: float, rotation=None):
        rot = rotation if rotation is not None else self.config.rotation
        if rot % 360 == 0:
            return w, h
        rad = math.radians(rot % 360)
        c = abs(math.cos(rad))
        s = abs(math.sin(rad))
        return w * c + h * s, w * s + h * c

    def _aabb_center_display(self) -> QPointF:
        return self._stamp_rect().center()

    def _rotation_handle_pos(self) -> QPointF:
        r = self._stamp_rect()
        if r.isEmpty():
            return QPointF()
        # handle sits north of box, above top edge
        # compute top-center, then offset north
        c = r.center()
        # for visual, handle position rotates with box? Keep orbit with box for intuitiveness
        # We'll place it north of the rotated box's top edge — i.e., from center, vector (0, -h/2 - offset) rotated
        rot = self.config.rotation % 360
        if rot == 0:
            return QPointF(c.x(), r.top() - ROTATION_HANDLE_OFFSET)
        # rotate offset vector
        rad = math.radians(rot)
        # vector from center to top-center is (0, -h/2)
        # we want center + rotate(0, -h/2 - offset)
        vx = 0
        vy = -r.height() / 2 - ROTATION_HANDLE_OFFSET
        rx = vx * math.cos(rad) - vy * math.sin(rad)
        ry = vx * math.sin(rad) + vy * math.cos(rad)
        return QPointF(c.x() + rx, c.y() + ry)

    def _rotated_polygon(self) -> QPolygonF:
        r = self._stamp_rect()
        if r.isEmpty():
            return QPolygonF()
        rot = self.config.rotation % 360
        if rot == 0:
            return QPolygonF(r)
        c = r.center()
        t = QTransform()
        t.translate(c.x(), c.y())
        t.rotate(rot)
        t.translate(-r.width() / 2, -r.height() / 2)
        return t.map(QPolygonF(QRectF(0, 0, r.width(), r.height())))

    def _ensure_rotation_fits(self):
        """Safest bounds: shift then shrink uniformly if rotated AABB still overflows."""
        if self._page_w <= 0 or self._page_h <= 0:
            return
        rot = self.config.rotation % 360
        if rot == 0:
            return
        # force keep_aspect when rotated
        if not self.config.keep_aspect:
            self.config.keep_aspect = True
        w_aabb, h_aabb = self._rotated_aabb_norm()
        new_x = self.config.rel_x
        new_y = self.config.rel_y
        new_w = self.config.rel_w
        new_h = self.config.rel_h
        changed = False
        # shrink if AABB larger than page
        if w_aabb > 1.0 or h_aabb > 1.0:
            scale = min(1.0 / max(0.001, w_aabb), 1.0 / max(0.001, h_aabb)) * 0.98
            scale = max(0.02, min(1.0, scale))
            new_w = max(0.02, new_w * scale)
            new_h = max(0.02, new_h * scale)
            w_aabb, h_aabb = self._rotated_aabb_norm(new_w, new_h, rot)
            changed = True
        # shift to fit
        # compute AABB origin: unrotated top-left is (rel_x, rel_y) in norm;
        # but rotated AABB's top-left is center - half_aabb
        # center in norm: cx = rel_x + rel_w/2, cy = rel_y + rel_h/2
        cx = new_x + new_w / 2
        cy = new_y + new_h / 2
        half_w = w_aabb / 2
        half_h = h_aabb / 2
        left = cx - half_w
        top = cy - half_h
        right = cx + half_w
        bottom = cy + half_h
        # shift center so AABB fits
        if left < 0:
            cx -= left
            changed = True
        if right > 1:
            cx -= (right - 1)
            changed = True
        if top < 0:
            cy -= top
            changed = True
        if bottom > 1:
            cy -= (bottom - 1)
            changed = True
        # recompute rel_x/y from adjusted center
        adj_x = cx - new_w / 2
        adj_y = cy - new_h / 2
        # also ensure unrotated rect itself not exceeding? Keep at least.
        adj_x = max(0, min(adj_x, 1 - new_w))
        adj_y = max(0, min(adj_y, 1 - new_h))
        if abs(adj_x - self.config.rel_x) > 1e-6:
            new_x = adj_x
            changed = True
        else:
            new_x = self.config.rel_x if not changed else adj_x
        if abs(adj_y - self.config.rel_y) > 1e-6:
            new_y = adj_y
            changed = True
        if abs(new_w - self.config.rel_w) > 1e-6:
            self.config.rel_w = new_w
            changed = True
        if abs(new_h - self.config.rel_h) > 1e-6:
            self.config.rel_h = new_h
            changed = True
        if abs(new_x - self.config.rel_x) > 1e-6:
            self.config.rel_x = new_x
            changed = True
        if abs(new_y - self.config.rel_y) > 1e-6:
            self.config.rel_y = new_y
            changed = True
        if changed:
            self.config_changed.emit(self.config)

    def _preserve_aspect_height_anchored(self):
        """Enforce static aspect on page switch — always, height-anchored.

        Per QA decision: preserve relative height (rel_h), recompute rel_w
        from image aspect so selector never warps when W/H changes.
        Overflow -> shift X to safest bounds (mathematically fit inside 0..1).
        Runs regardless of keep_aspect (decision A) — lock only affects drag.
        """
        if not self._stamp_pixmap or self._stamp_pixmap.isNull():
            return
        if self._page_w <= 0 or self._page_h <= 0:
            return
        aspect = self._stamp_pixmap.width() / max(1, self._stamp_pixmap.height())
        if aspect <= 0:
            return
        cur_h = max(0.02, min(0.98, self.config.rel_h))
        new_w = cur_h * aspect * self._page_h / max(0.001, self._page_w)
        new_w = max(0.02, min(0.98, new_w))
        new_x = self.config.rel_x
        # safest bounds: shift left if overflow, else keep left anchored
        if new_x + new_w > 1.0:
            new_x = 1.0 - new_w
            if new_x < 0:
                new_x = 0
                if new_x + new_w > 1.0:
                    new_w = 1.0 - new_x
                    new_w = max(0.02, new_w)
        new_y = self.config.rel_y
        if new_y + cur_h > 1.0:
            new_y = max(0.0, 1.0 - cur_h)
        changed = False
        if abs(new_w - self.config.rel_w) > 1e-6:
            self.config.rel_w = new_w
            changed = True
        if abs(new_x - self.config.rel_x) > 1e-6:
            self.config.rel_x = new_x
            changed = True
        if abs(cur_h - self.config.rel_h) > 1e-6:
            self.config.rel_h = cur_h
            changed = True
        if abs(new_y - self.config.rel_y) > 1e-6:
            self.config.rel_y = new_y
            changed = True
        if changed:
            self.config_changed.emit(self.config)
        # after aspect fix, ensure rotated AABB still fits
        if self.config.rotation % 360 != 0:
            self._ensure_rotation_fits()

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
        # keep current page's box aspect-static even on stamp swap
        if self._pixmap:
            self._preserve_aspect_height_anchored()
            if self.config.rotation % 360 != 0:
                self._ensure_rotation_fits()
        self.update()

    def set_config(self, config: StampConfig):
        self.config = config
        self.config.normalize_rotation()
        # force keep_aspect if rotated
        if self.config.rotation % 360 != 0 and not self.config.keep_aspect:
            self.config.keep_aspect = True
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
            # always keep aspect static on page change — height anchored, safest bounds
            self._preserve_aspect_height_anchored()
            if self.config.rotation % 360 != 0:
                self._ensure_rotation_fits()
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
        # hide resize handles when rotated — force keep_aspect, avoid shear
        if self.config.rotation % 360 != 0:
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
        # rotation handle highest priority
        if self._pixmap and self.config.rotation is not None:
            # only when stamp rect valid
            r = self._stamp_rect()
            if not r.isEmpty():
                hp = self._rotation_handle_pos()
                if math.hypot(pos.x() - hp.x(), pos.y() - hp.y()) <= ROTATION_HANDLE_RADIUS + 4:
                    return "rotate"
        # resize handles only when not rotated
        for k, rect in self._handle_rects().items():
            if rect.contains(pos):
                return k
        # move test: polygon contains
        poly = self._rotated_polygon()
        if not poly.isEmpty() and poly.containsPoint(pos, Qt.OddEvenFill):
            return "move"
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
        rot = self.config.rotation % 360 if self.config.rotation else 0
        # draw stamp pixmap
        if self._stamp_pixmap and not self._stamp_pixmap.isNull():
            if rot == 0:
                painter.setOpacity(0.85)
                painter.drawPixmap(r.toRect(), self._stamp_pixmap)
                painter.setOpacity(1.0)
            else:
                painter.save()
                c = r.center()
                painter.translate(c)
                painter.rotate(rot)
                painter.translate(-r.width() / 2, -r.height() / 2)
                painter.setOpacity(0.85)
                painter.drawPixmap(QRectF(0, 0, r.width(), r.height()).toRect(), self._stamp_pixmap)
                painter.setOpacity(1.0)
                painter.restore()
        else:
            # placeholder
            if rot == 0:
                painter.setBrush(QBrush(QColor(0, 191, 255, 40)))
                painter.drawRect(r)
                painter.setBrush(QBrush(Qt.NoBrush))
            else:
                poly = self._rotated_polygon()
                painter.setBrush(QBrush(QColor(0, 191, 255, 40)))
                painter.setPen(Qt.NoPen)
                painter.drawPolygon(poly)
                painter.setBrush(QBrush(Qt.NoBrush))

        # outline
        painter.setPen(QPen(QColor("#00BFFF"), 2, Qt.DashLine))
        painter.setBrush(QBrush(Qt.NoBrush))
        if rot == 0:
            painter.drawRect(r)
        else:
            painter.drawPolygon(self._rotated_polygon())

        # handles / rotation handle
        painter.setPen(QPen(QColor("#00BFFF"), 1))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        if rot == 0:
            for rect in self._handle_rects().values():
                painter.drawRect(rect)
        # always draw rotation handle
        hp = self._rotation_handle_pos()
        if not hp.isNull():
            # line from top-center to handle
            if rot == 0:
                c_top = QPointF(r.center().x(), r.top())
            else:
                # top-center of rotated polygon is approximated by handle line start
                # we have center and handle pos, line from near edge to handle
                poly = self._rotated_polygon()
                # find closest point on polygon edge to handle — approximate using handle offset
                # simple: line from center towards handle, intersection at half-height
                rad = math.radians(rot)
                vx = 0
                vy = -r.height() / 2
                rx = vx * math.cos(rad) - vy * math.sin(rad)
                ry = vx * math.sin(rad) + vy * math.cos(rad)
                c_top = QPointF(r.center().x() + rx, r.center().y() + ry)
            painter.setPen(QPen(QColor("#00BFFF"), 1, Qt.SolidLine))
            painter.drawLine(c_top, hp)
            painter.setPen(QPen(QColor("#00BFFF"), 1))
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            painter.drawEllipse(hp, ROTATION_HANDLE_RADIUS, ROTATION_HANDLE_RADIUS)
            # small arc indicator
            painter.setBrush(QBrush(Qt.NoBrush))
            painter.drawEllipse(hp, 3, 3)

        painter.setPen(QColor("#FFF"))
        painter.drawText(
            int(r.left()), int(max(12, r.top() - 4)),
            f"{self._page_w:.0f} x {self._page_h:.0f} pt  {rot:.0f}°"
        )

    def mousePressEvent(self, event):
        if not self._pixmap or event.button() != Qt.LeftButton:
            return
        pos = QPointF(event.position())
        hit = self._hit_test(pos)
        if not hit:
            return
        if hit == "rotate":
            self._rotating = True
            c = self._aabb_center_display()
            self._rotate_start_angle = math.degrees(math.atan2(pos.y() - c.y(), pos.x() - c.x()))
            self._rotate_orig = self.config.rotation
            self._orig_rect = self._stamp_rect()
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
        if not self._dragging and not self._resizing and not self._rotating:
            hit = self._hit_test(pos)
            if hit == "rotate":
                self.setCursor(Qt.CrossCursor)
            elif hit in ("tl", "br"):
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

        if self._rotating:
            c = self._aabb_center_display()
            cur_ang = math.degrees(math.atan2(pos.y() - c.y(), pos.x() - c.x()))
            delta = cur_ang - self._rotate_start_angle
            new_rot = (self._rotate_orig + delta) % 360
            if self.config.rotation_snap_90:
                new_rot = round(new_rot / 90) * 90 % 360
            # force keep_aspect
            if new_rot % 360 != 0 and not self.config.keep_aspect:
                self.config.keep_aspect = True
            self.config.rotation = new_rot
            self._ensure_rotation_fits()
            self.update()
            self.config_changed.emit(self.config)
            return

        dx = pos.x() - self._drag_start.x()
        dy = pos.y() - self._drag_start.y()

        if self._dragging:
            rot = self.config.rotation % 360 if self.config.rotation else 0
            if rot == 0:
                new_x = self._orig_rect.x() + dx
                new_y = self._orig_rect.y() + dy
                new_x = max(d.left(), min(new_x, d.right() - self._orig_rect.width()))
                new_y = max(d.top(), min(new_y, d.bottom() - self._orig_rect.height()))
                self.config.rel_x = (new_x - d.x()) / d.width()
                self.config.rel_y = (new_y - d.y()) / d.height()
            else:
                # use center + AABB half extents for clamp
                w = self._orig_rect.width()
                h = self._orig_rect.height()
                hw2, hh2 = self._rotated_aabb_display(w, h, rot)
                hw2 /= 2
                hh2 /= 2
                c0 = self._orig_rect.center()
                nc = QPointF(c0.x() + dx, c0.y() + dy)
                nc.setX(max(d.left() + hw2, min(nc.x(), d.right() - hw2)))
                nc.setY(max(d.top() + hh2, min(nc.y(), d.bottom() - hh2)))
                # convert back to rel_x/y from center
                new_x = nc.x() - w / 2
                new_y = nc.y() - h / 2
                self.config.rel_x = (new_x - d.x()) / d.width()
                self.config.rel_y = (new_y - d.y()) / d.height()
                # post-move ensure still fits (shrinks if needed)
                self._ensure_rotation_fits()
            self.update()
            self.config_changed.emit(self.config)
            return

        if self._resizing:
            # when rotated, resizing is disabled via _handle_rects -> shouldn't reach here
            if self.config.rotation % 360 != 0:
                return
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
        self._rotating = False
        self._resize_dir = None
        self.setCursor(Qt.ArrowCursor)
