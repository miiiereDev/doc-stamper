import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path
import tempfile, shutil, math, io
import fitz
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF
from autostamper.config import StampConfig
from autostamper.canvas import PDFCanvasWidget
from autostamper.main_window import MainWindow
from autostamper.image import rotated_aabb, prepare_stamp_bytes

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


def test_default_keep_aspect_true_and_rotation():
    c = StampConfig()
    assert c.keep_aspect is True
    assert c.rotation == 0.0
    assert not c.rotation_snap_90


def test_rotated_aabb_math():
    w, h = rotated_aabb(0.2, 0.1, 612, 792, 0)
    assert abs(w - 0.2) < 1e-6 and abs(h - 0.1) < 1e-6
    w90, h90 = rotated_aabb(0.2, 0.1, 612, 792, 90)
    # swap scaled by page ratio: w_px 122.4 h_px 79.2 -> w2 ~79.2, h2 ~122.4 -> norm
    assert abs(w90 - 79.2/612) < 0.01
    assert abs(h90 - 122.4/792) < 0.01
    w45, h45 = rotated_aabb(0.2, 0.1, 612, 792, 45)
    assert w45 > 0.2 and h45 > 0.1
    assert w45 < 1 and h45 < 1


def test_canvas_rotation_forces_keep_aspect():
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    cfg = StampConfig(rel_x=0.1, rel_y=0.1, rel_w=0.2, rel_h=0.1, keep_aspect=False, rotation=0)
    w = PDFCanvasWidget(cfg)
    w.resize(800, 600); w.show(); app.processEvents()
    w.set_stamp(str(stamp))
    w.load_pdf(tmp / "a4.pdf"); app.processEvents()
    # set via canvas set_config with rotation 45 and keep_aspect False -> should force True
    cfg.rotation = 45
    cfg.keep_aspect = False
    w.set_config(cfg)
    assert w.config.keep_aspect is True
    assert w.config.rotation == 45
    w.close(); shutil.rmtree(str(tmp), ignore_errors=True)


def test_canvas_preview_rotated_does_not_crash():
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    cfg = StampConfig(rel_x=0.1, rel_y=0.1, rel_w=0.2, rel_h=0.1, rotation=45)
    w = PDFCanvasWidget(cfg)
    w.resize(800, 600); w.show(); app.processEvents()
    w.set_stamp(str(stamp))
    w.load_pdf(tmp / "a4.pdf"); app.processEvents()
    # trigger paint
    w.repaint(); app.processEvents()
    assert w._pixmap is not None
    # handle pos exists
    hp = w._rotation_handle_pos()
    assert not hp.isNull()
    poly = w._rotated_polygon()
    assert not poly.isEmpty()
    assert poly.count() >= 4
    w.close(); shutil.rmtree(str(tmp), ignore_errors=True)


def test_snap_90_toggle():
    c = StampConfig(rotation=37, rotation_snap_90=True)
    c.normalize_rotation()
    assert c.rotation == 0
    c.rotation = 47; c.normalize_rotation(); assert c.rotation == 90
    c.rotation = 136; c.normalize_rotation(); assert c.rotation == 180
    # granular
    c.rotation_snap_90 = False
    c.rotation = 37; c.normalize_rotation(); assert c.rotation == 37
    # canvas handle snapping
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    cfg = StampConfig(rotation_snap_90=True, rotation=0)
    w = PDFCanvasWidget(cfg)
    w.resize(800, 600); w.show(); app.processEvents()
    w.set_stamp(str(stamp)); w.load_pdf(tmp / "a4.pdf"); app.processEvents()
    # simulate rotating via mouse — we test normalization via config
    cfg.rotation = 37; cfg.normalize_rotation(); w.set_config(cfg)
    assert w.config.rotation == 0
    w.close(); shutil.rmtree(str(tmp), ignore_errors=True)


def test_ensure_rotation_fits_safest_bounds():
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    # place near right edge with rotation 45, AABB will overflow -> should shift
    cfg = StampConfig(rel_x=0.85, rel_y=0.1, rel_w=0.2, rel_h=0.1, rotation=45)
    w = PDFCanvasWidget(cfg)
    w.resize(800, 600); w.show(); app.processEvents()
    w.set_stamp(str(stamp))
    w.load_pdf(tmp / "a4.pdf"); app.processEvents()
    # after load, _ensure_rotation_fits should have shifted
    w_aabb, h_aabb = w._rotated_aabb_norm()
    cx = w.config.rel_x + w.config.rel_w/2
    cy = w.config.rel_y + w.config.rel_h/2
    assert cx - w_aabb/2 >= -1e-6
    assert cx + w_aabb/2 <= 1+1e-6
    assert cy - h_aabb/2 >= -1e-6
    assert cy + h_aabb/2 <= 1+1e-6
    assert w.config.rel_x >= 0 and w.config.rel_y >= 0
    w.close(); shutil.rmtree(str(tmp), ignore_errors=True)


def test_ensure_rotation_fits_shrink_when_overflows():
    # huge box at 45 will be >1 AABB, should shrink
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    cfg = StampConfig(rel_x=0.1, rel_y=0.1, rel_w=0.8, rel_h=0.6, rotation=45)
    w = PDFCanvasWidget(cfg)
    w.resize(800, 600); w.show(); app.processEvents()
    w.set_stamp(str(stamp))
    w.load_pdf(tmp / "a4.pdf"); app.processEvents()
    w_aabb, h_aabb = w._rotated_aabb_norm()
    assert w_aabb <= 1.0 + 1e-6 and h_aabb <= 1.0 + 1e-6
    # also check orig rel stays within 0.02..0.98
    assert 0.02 <= w.config.rel_w <= 0.98
    assert 0.02 <= w.config.rel_h <= 0.98
    w.close(); shutil.rmtree(str(tmp), ignore_errors=True)


def test_prepare_stamp_bytes():
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    b0 = prepare_stamp_bytes(stamp, 0)
    assert b0
    b90 = prepare_stamp_bytes(stamp, 90)
    assert b90 and b90 != b0
    # check rotated is valid PNG via PIL
    im = Image.open(io.BytesIO(b90))
    assert im.size[0] == 100 and im.size[1] == 300  # 300x100 rotated 90 -> 100x300
    shutil.rmtree(str(tmp), ignore_errors=True)


def test_worker_rotation_inserts():
    tmp = Path(tempfile.mkdtemp())
    out = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    pdf = tmp / "a4.pdf"
    # use config rotation 90
    cfg = StampConfig(rel_x=0.1, rel_y=0.1, rel_w=0.2, rel_h=0.1, rotation=90, keep_aspect=True, target_page="last")
    # directly test insertion without thread
    doc = fitz.open(str(pdf))
    page = doc[0]
    W, H = float(page.rect.width), float(page.rect.height)
    rect = fitz.Rect(cfg.rel_x*W, cfg.rel_y*H, (cfg.rel_x+cfg.rel_w)*W, (cfg.rel_y+cfg.rel_h)*H)
    data = prepare_stamp_bytes(stamp, cfg.rotation)
    pix = fitz.Pixmap(data)
    page.insert_image(rect, pixmap=pix, keep_proportion=True, overlay=True)
    out_pdf = out / "out.pdf"
    doc.save(str(out_pdf), garbage=3, deflate=True)
    doc.close()
    doc2 = fitz.open(str(out_pdf))
    assert len(doc2[0].get_images(full=True)) == 1
    doc2.close()
    shutil.rmtree(str(tmp), ignore_errors=True)
    shutil.rmtree(str(out), ignore_errors=True)


def test_mainwindow_rotation_sync_and_force():
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    win = MainWindow()
    win.resize(1000, 700); win.show(); app.processEvents()
    # default keep_aspect True
    assert win.aspect_check.isChecked() is True
    assert win.aspect_check.isEnabled() is True
    # set rotation via nudge
    win.nudge_rotation(45); app.processEvents()
    assert win.config.rotation == 45
    assert win.aspect_check.isChecked() is True
    assert win.aspect_check.isEnabled() is False  # forced
    # try to uncheck aspect -> should stay checked
    win.aspect_check.setChecked(False); app.processEvents()
    assert win.aspect_check.isChecked() is True
    # toggle snap
    win.snap_check.setChecked(True); app.processEvents()
    assert win.config.rotation_snap_90 is True
    # granular off: rotation snaps to 90
    win.config.rotation = 37
    win.config.normalize_rotation()
    assert win.config.rotation == 0
    # back to granular, move slider
    win.snap_check.setChecked(False); app.processEvents()
    win.rotation_slider.setValue(30); app.processEvents()
    assert win.config.rotation == 30
    # handle that toggle updates slider step
    assert win.rotation_slider.singleStep() == 1
    win.snap_check.setChecked(True); app.processEvents()
    assert win.rotation_slider.singleStep() == 90
    win.close(); shutil.rmtree(str(tmp), ignore_errors=True)


def test_manual_stamp_current_with_rotation(tmp_path=None):
    # integration: MainWindow.manual_stamp_current with rotated config
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    stamp = _tmp_pdfs(tmp)
    # need separate input folder
    inp = Path(tempfile.mkdtemp())
    # copy pdf to input
    import shutil as sh
    sh.copy(str(tmp / "a4.pdf"), str(inp / "a4.pdf"))
    win = MainWindow()
    win.resize(1000, 700); win.show(); app.processEvents()
    win.input_edit.setText(str(inp))
    win.stamp_edit.setText(str(stamp))
    win.canvas.set_stamp(str(stamp))
    win.scan_pdfs(inp); app.processEvents()
    win.config.rotation = 45
    win.config.keep_aspect = True
    win.canvas.set_config(win.config)
    win.manual_stamp_current()
    app.processEvents()
    out = inp / ".stamped" / "a4.pdf"
    assert out.exists()
    doc = fitz.open(str(out))
    assert len(doc[0].get_images(full=True)) == 1
    doc.close()
    win.close()
    sh.rmtree(str(tmp), ignore_errors=True)
    sh.rmtree(str(inp), ignore_errors=True)
