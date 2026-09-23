import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path
import tempfile, shutil
import fitz
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication
from autostamper.main_window import MainWindow

app = QApplication.instance() or QApplication([])


def _make_sample(tmp: Path):
    for name, w, h in [("a.pdf", 595, 842), ("b.pdf", 612, 792)]:
        doc = fitz.open()
        doc.new_page(width=w, height=h)
        doc.save(tmp / name)
        doc.close()
    stamp = tmp / "stamp.png"
    img = Image.new("RGBA", (200, 80), (255, 0, 0, 128))
    ImageDraw.Draw(img).text((10, 10), "X", fill=(255, 255, 255, 255))
    img.save(stamp)
    return stamp


def test_default_manual():
    w = MainWindow()
    w.resize(1000, 700)
    w.show()
    app.processEvents()
    assert w.mode == "manual"
    assert w.radio_manual.isChecked()
    assert w.stack.currentIndex() == 0
    # lock and start are inside auto panel, should not be visible in manual
    assert not w.start_btn.isVisible()
    assert not w.lock_btn.isVisible()
    assert w.manual_stamp_btn.isVisible()
    w.close()


def test_switch_to_auto_shows_batch_controls():
    w = MainWindow()
    w.resize(1000, 700)
    w.show()
    app.processEvents()
    w.radio_auto.setChecked(True)
    app.processEvents()
    assert w.mode == "auto"
    assert w.stack.currentIndex() == 1
    assert w.lock_btn.isVisible()
    assert w.start_btn.isVisible()
    assert not w.manual_stamp_btn.isVisible()
    # aspect stays visible in both
    assert w.aspect_check.isVisible()
    w.close()


def test_manual_stamp_one_by_one():
    tmp = Path(tempfile.mkdtemp())
    stamp = _make_sample(tmp)
    w = MainWindow()
    w.resize(1000, 700)
    w.show()
    app.processEvents()
    w.input_edit.setText(str(tmp))
    w.stamp_edit.setText(str(stamp))
    w.canvas.set_stamp(str(stamp))
    w.scan_pdfs(tmp)
    app.processEvents()
    assert len(w.pdf_paths) == 2
    assert w.manual_index == 0
    assert "File 1 of 2" in w.manual_info.text()
    # stamp first
    w.manual_stamp_current()
    app.processEvents()
    assert w.table.item(0, 1).text() == "Done"
    out = tmp / ".stamped" / "a.pdf"
    assert out.exists()
    # should auto advance to 1
    assert w.manual_index == 1
    assert "File 2 of 2" in w.manual_info.text()
    # stamp second
    w.manual_stamp_current()
    app.processEvents()
    assert w.table.item(1, 1).text() == "Done"
    assert (tmp / ".stamped" / "b.pdf").exists()
    assert w.progress.value() == 100
    w.close()
    shutil.rmtree(tmp, ignore_errors=True)


def test_manual_skip_and_navigation():
    tmp = Path(tempfile.mkdtemp())
    stamp = _make_sample(tmp)
    w = MainWindow()
    w.show()
    app.processEvents()
    w.input_edit.setText(str(tmp))
    w.stamp_edit.setText(str(stamp))
    w.canvas.set_stamp(str(stamp))
    w.scan_pdfs(tmp)
    app.processEvents()
    # skip first
    w.manual_skip_current()
    app.processEvents()
    assert w.table.item(0, 1).text() == "Skipped"
    assert w.manual_index == 1
    # prev
    w.manual_prev_file()
    app.processEvents()
    assert w.manual_index == 0
    assert w.canvas._pdf_path.name == "a.pdf"
    w.close()
    shutil.rmtree(tmp, ignore_errors=True)


def test_auto_mode_still_batch():
    # verify auto batch still works via worker path
    tmp = Path(tempfile.mkdtemp())
    stamp = _make_sample(tmp)
    w = MainWindow()
    w.show()
    app.processEvents()
    w.radio_auto.setChecked(True)
    app.processEvents()
    w.input_edit.setText(str(tmp))
    w.stamp_edit.setText(str(stamp))
    w.canvas.set_stamp(str(stamp))
    w.scan_pdfs(tmp)
    app.processEvents()
    assert w.mode == "auto"
    assert w.start_btn.isEnabled()
    w.close()
    shutil.rmtree(tmp, ignore_errors=True)
