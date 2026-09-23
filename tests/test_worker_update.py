import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import threading, shutil
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from autostamper.config import StampConfig
from autostamper.worker import StamperWorker
import fitz

app = QApplication([])
inp = Path("tests")
shutil.rmtree(inp / ".stamped", ignore_errors=True)
pdfs = sorted(list(inp.glob("*.pdf")))  # a4, letter - order alphabetical a4 first
# reverse to have letter first then a4 to test update
pdfs = [Path("tests/letter.pdf"), Path("tests/a4.pdf")]
stamp = Path("tests/stamp.png")
cfg = StampConfig(rel_x=0.2, rel_y=0.2, rel_w=0.15, rel_h=0.15, target_page="last", tolerance=3.0, is_locked=True, std_width=612, std_height=792)
ev = threading.Event()
worker = StamperWorker(pdfs, stamp, cfg, ev, inp)
mismatches=[]

def on_mismatch(path, idx, w, h):
    print(f"MISMATCH {Path(path).name} {w}x{h}")
    mismatches.append(path)
    # simulate user choosing Set as New Standard
    QTimer.singleShot(200, worker.resume_update_standard)

def on_finished():
    print(f"cfg after {cfg.std_width}x{cfg.std_height}")
    # after a4 mismatch and update, cfg should be a4 size
    assert cfg.std_width == 595 and cfg.std_height == 842, f"expected updated to 595,842 got {cfg.std_width},{cfg.std_height}"
    print("update_standard PASS")
    app.quit()

worker.mismatch_detected.connect(on_mismatch)
worker.finished.connect(on_finished)
worker.start()
QTimer.singleShot(10000, lambda: (print("TIMEOUT"), app.quit()))
app.exec()
print("DONE mismatches", mismatches)

# skip test
print("\n--- skip test ---")
shutil.rmtree(inp / ".stamped", ignore_errors=True)
cfg2 = StampConfig(rel_x=0.1, rel_y=0.1, rel_w=0.2, rel_h=0.1, target_page="last", tolerance=3.0, is_locked=True, std_width=612, std_height=792)
ev2 = threading.Event()
pdfs2 = [Path("tests/a4.pdf"), Path("tests/letter.pdf")]
app2 = QApplication.instance()
if not app2:
    app2 = QApplication([])
worker2 = StamperWorker(pdfs2, stamp, cfg2, ev2, inp)
def on_mismatch2(path, idx, w, h):
    print(f"MISMATCH2 {Path(path).name}")
    QTimer.singleShot(200, worker2.resume_skip)
def on_finished2():
    print("skip finished")
    # a4 should be skipped (not exist), letter should exist
    print(f"a4 exists { (inp/'.stamped'/'a4.pdf').exists()} letter exists {(inp/'.stamped'/'letter.pdf').exists()}")
    assert not (inp/'.stamped'/'a4.pdf').exists()
    assert (inp/'.stamped'/'letter.pdf').exists()
    print("skip PASS")
    app.quit()
worker2.mismatch_detected.connect(on_mismatch2)
worker2.finished.connect(on_finished2)
worker2.start()
QTimer.singleShot(10000, lambda: (print("TIMEOUT2"), app.quit()))
app.exec()
