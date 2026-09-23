import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path
import tempfile, shutil
import fitz
from PIL import Image
from PySide6.QtWidgets import QApplication
from autostamper.config import StampConfig
from autostamper.canvas import PDFCanvasWidget
from autostamper.main_window import MainWindow

app = QApplication.instance() or QApplication([])


def _tmp_pdfs(tmp: Path):
    for name, w, h in [("a4.pdf", 595, 842), ("letter.pdf", 612, 792)]:
        d = fitz.open()
        d.new_page(width=w, height=h)
        d.save(str(tmp / name))
        d.close()
    stamp = tmp / "stamp.png"
    Image.new("RGBA", (300, 100), (255, 0, 0, 255)).save(str(stamp))
    return stamp


def test_height_anchored_preserves_aspect_on_switch():
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    cfg = StampConfig(rel_x=0.1, rel_y=0.2, rel_w=0.424, rel_h=0.1, keep_aspect=False)
    w = PDFCanvasWidget(cfg)
    w.resize(800, 600); w.show(); app.processEvents()
    w.set_stamp(str(stamp))
    w.load_pdf(tmp / "a4.pdf"); app.processEvents()
    aspect_a4 = (w.config.rel_w * w._page_w) / (w.config.rel_h * w._page_h)
    assert abs(aspect_a4 - 3.0) < 0.02, f"a4 aspect {aspect_a4}"
    assert abs(w.config.rel_h - 0.1) < 1e-6  # height preserved
    w.load_pdf(tmp / "letter.pdf"); app.processEvents()
    aspect_letter = (w.config.rel_w * w._page_w) / (w.config.rel_h * w._page_h)
    assert abs(aspect_letter - 3.0) < 0.02, f"letter aspect {aspect_letter}"
    assert abs(w.config.rel_h - 0.1) < 1e-6
    # height anchored: letter width should be rel_h*3*H/W = 0.1*3*792/612
    expected_w = 0.1 * 3 * 792 / 612
    assert abs(w.config.rel_w - expected_w) < 0.01
    w.close(); shutil.rmtree(str(tmp), ignore_errors=True)


def test_always_preserves_even_when_unlocked():
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    for keep in (True, False):
        cfg = StampConfig(rel_x=0.1, rel_y=0.1, rel_w=0.3, rel_h=0.1, keep_aspect=keep)
        w = PDFCanvasWidget(cfg)
        w.resize(800, 600); w.show(); app.processEvents()
        w.set_stamp(str(stamp))
        w.load_pdf(tmp / "a4.pdf"); app.processEvents()
        w.load_pdf(tmp / "letter.pdf"); app.processEvents()
        aspect = (w.config.rel_w * w._page_w) / (w.config.rel_h * w._page_h)
        assert abs(aspect - 3.0) < 0.02, f"keep={keep} aspect {aspect}"
        w.close()
    shutil.rmtree(str(tmp), ignore_errors=True)


def test_overflow_shifts_to_safe_bounds():
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    # place at far right, will overflow when width recomputed
    cfg = StampConfig(rel_x=0.85, rel_y=0.1, rel_w=0.2, rel_h=0.1, keep_aspect=False)
    w = PDFCanvasWidget(cfg)
    w.resize(800, 600); w.show(); app.processEvents()
    w.set_stamp(str(stamp))
    w.load_pdf(tmp / "a4.pdf"); app.processEvents()
    # after A4 load, should have been shifted to fit: x+ w <=1
    assert w.config.rel_x + w.config.rel_w <= 1.0 + 1e-6
    assert w.config.rel_x >= 0
    # ensure aspect still 3
    aspect = (w.config.rel_w * w._page_w) / (w.config.rel_h * w._page_h)
    assert abs(aspect - 3.0) < 0.02
    # switch to letter, again should stay in bounds
    w.load_pdf(tmp / "letter.pdf"); app.processEvents()
    assert w.config.rel_x + w.config.rel_w <= 1.0 + 1e-6
    aspect2 = (w.config.rel_w * w._page_w) / (w.config.rel_h * w._page_h)
    assert abs(aspect2 - 3.0) < 0.02
    w.close(); shutil.rmtree(str(tmp), ignore_errors=True)


def test_no_stamp_no_correction():
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    cfg = StampConfig(rel_x=0.1, rel_y=0.1, rel_w=0.2, rel_h=0.15, keep_aspect=False)
    w = PDFCanvasWidget(cfg)
    w.resize(800, 600); w.show(); app.processEvents()
    # no set_stamp
    w.load_pdf(tmp / "a4.pdf"); app.processEvents()
    assert abs(w.config.rel_w - 0.2) < 1e-6
    assert abs(w.config.rel_h - 0.15) < 1e-6
    w.load_pdf(tmp / "letter.pdf"); app.processEvents()
    assert abs(w.config.rel_w - 0.2) < 1e-6
    assert abs(w.config.rel_h - 0.15) < 1e-6
    w.close(); shutil.rmtree(str(tmp), ignore_errors=True)


def test_mainwindow_manual_navigation_preserves():
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    win = MainWindow()
    win.resize(1000, 700); win.show(); app.processEvents()
    win.input_edit.setText(str(tmp))
    win.stamp_edit.setText(str(stamp))
    win.canvas.set_stamp(str(stamp))
    win.scan_pdfs(tmp); app.processEvents()
    # set known height anchored box on A4
    win.config.rel_h = 0.1
    win.config.rel_w = 0.4
    win.config.rel_x = 0.1
    win.canvas.set_config(win.config); app.processEvents()
    # force A4 then letter
    win.canvas.load_pdf(tmp / "a4.pdf"); app.processEvents()
    win.canvas.load_pdf(tmp / "letter.pdf"); app.processEvents()
    aspect = (win.config.rel_w * win.canvas._page_w) / (win.config.rel_h * win.canvas._page_h)
    assert abs(aspect - 3.0) < 0.05
    assert abs(win.config.rel_h - 0.1) < 1e-6
    assert win.config.rel_x + win.config.rel_w <= 1.0 + 1e-6
    win.close(); shutil.rmtree(str(tmp), ignore_errors=True)
