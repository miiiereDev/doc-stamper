import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path
import fitz
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRectF, QPointF
from autostamper.config import StampConfig
from autostamper.canvas import PDFCanvasWidget

app = QApplication.instance() or QApplication([])


def _make_widget():
    cfg = StampConfig(rel_x=0.1, rel_y=0.1, rel_w=0.2, rel_h=0.15)
    w = PDFCanvasWidget(cfg)
    w.resize(800, 600)
    w.show()
    app.processEvents()
    return w


def test_normalized_coords():
    cfg = StampConfig(rel_x=0.25, rel_y=0.3, rel_w=0.2, rel_h=0.1)
    assert cfg.is_valid()
    w = _make_widget()
    w.config = cfg
    # simulate display rect 400x400 at 10,10
    w._offset_x = 10
    w._offset_y = 10
    w._draw_w = 400
    w._draw_h = 400
    w._pixmap = w._pixmap or __import__("PySide6.QtGui", fromlist=["QPixmap"]).QPixmap(400, 400)
    r = w._stamp_rect()
    assert abs(r.x() - (10 + 0.25 * 400)) < 1e-6
    assert abs(r.y() - (10 + 0.3 * 400)) < 1e-6
    assert abs(r.width() - 0.2 * 400) < 1e-6
    assert abs(r.height() - 0.1 * 400) < 1e-6
    w.close()


def test_display_rect_empty_without_pixmap():
    w = _make_widget()
    w._pixmap = None
    assert w._display_rect().isEmpty()
    assert w._stamp_rect().isEmpty()
    w.close()


def test_load_pdf_sets_dimensions(tmp_path=Path("tests")):
    # create fixture
    p = Path("tests/_tmp_canvas.pdf")
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.save(str(p))
    doc.close()
    w = _make_widget()
    ok = w.load_pdf(p, "last")
    assert ok
    assert w._page_w == 612
    assert w._page_h == 792
    assert w._pixmap is not None
    w.close()
    p.unlink(missing_ok=True)


def test_stamp_preview_set():
    w = _make_widget()
    # ensure stamp pixmap initially None
    assert w._stamp_pixmap is None
    # set nonexistent path
    w.set_stamp(Path("nonexistent.png"))
    assert w._stamp_pixmap is None
    # create real png
    png = Path("tests/_tmp_stamp.png")
    from PIL import Image
    Image.new("RGBA", (100, 50), (255, 0, 0, 128)).save(str(png))
    w.set_stamp(png)
    assert w._stamp_pixmap is not None
    assert not w._stamp_pixmap.isNull()
    png.unlink(missing_ok=True)
    w.close()


def test_aspect_lock_enforced_on_resize():
    w = _make_widget()
    cfg = StampConfig(rel_x=0.1, rel_y=0.1, rel_w=0.2, rel_h=0.1, keep_aspect=True)
    w.config = cfg
    # fake display
    w._offset_x = 0
    w._offset_y = 0
    w._draw_w = 400
    w._draw_h = 400
    w._pixmap = w._pixmap or __import__("PySide6.QtGui", fromlist=["QPixmap"]).QPixmap(400, 400)
    # need stamp pixmap for aspect
    from PIL import Image
    png = Path("tests/_tmp_aspect.png")
    Image.new("RGBA", (300, 100), (255, 0, 0, 255)).save(str(png))
    from PySide6.QtGui import QPixmap
    w._stamp_pixmap = QPixmap(str(png))
    # orig rect
    w._orig_rect = w._stamp_rect()
    w._resize_dir = "br"
    w._resizing = True
    # simulate dx 100, dy 0 would warp without lock; with lock should keep 3:1
    r = QRectF(w._orig_rect)
    w._drag_start = QPointF(r.right(), r.bottom())
    # emulate mouse move to +100,0
    # directly call resizing logic via mouseMoveEvent
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import Qt
    new_pos = QPointF(r.right() + 100, r.bottom())
    evt = QMouseEvent(QEvent.MouseMove, new_pos, new_pos, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    w.mouseMoveEvent(evt)
    # after, display aspect should be ~3
    r2 = w._stamp_rect()
    disp_aspect = r2.width() / max(1, r2.height())
    assert abs(disp_aspect - 3.0) < 0.2, f"aspect {disp_aspect} not ~3"
    png.unlink(missing_ok=True)
    w.close()
