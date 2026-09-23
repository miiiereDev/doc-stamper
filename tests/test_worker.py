import threading
from pathlib import Path

# offscreen for CI
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from autostamper.config import StampConfig
from autostamper.worker import StamperWorker
import fitz

app = QApplication([])

inp = Path("tests")
# clean previous stamped
import shutil
shutil.rmtree(inp / ".stamped", ignore_errors=True)

pdfs = sorted(list(inp.glob("*.pdf")))
stamp = Path("tests/stamp.png")

cfg = StampConfig(rel_x=0.1, rel_y=0.1, rel_w=0.2, rel_h=0.1, target_page="last", tolerance=3.0, is_locked=True, std_width=612, std_height=792)
ev = threading.Event()
worker = StamperWorker(pdfs, stamp, cfg, ev, inp)

mismatches = []
progresses = []
statuses = []

def on_mismatch(path, idx, w, h):
    print(f"MISMATCH {Path(path).name} {w}x{h}")
    mismatches.append((path, w, h))
    # after 200ms resolve as apply_once
    QTimer.singleShot(200, worker.resume_apply_once)

def on_progress(done, total, name):
    print(f"PROGRESS {done}/{total} {name}")
    progresses.append((done, name))

def on_status(path, status):
    print(f"STATUS {Path(path).name} {status}")
    statuses.append(status)

def on_finished():
    print("FINISHED")
    print(f"cfg after {cfg.std_width}x{cfg.std_height} locked {cfg.is_locked}")
    for p in pdfs:
        out = inp / ".stamped" / p.name
        print(f"{p.name} stamped exists {out.exists()} size {out.stat().st_size if out.exists() else 0}")
        # verify stamp inserted by checking image count
        doc = fitz.open(str(out))
        page = doc[0]
        imgs = page.get_images()
        print(f"  images on page {len(imgs)}")
        doc.close()
    app.quit()

worker.mismatch_detected.connect(on_mismatch)
worker.progress.connect(on_progress)
worker.file_status.connect(on_status)
worker.finished.connect(on_finished)

worker.start()

# safety timeout
QTimer.singleShot(10000, lambda: (print("TIMEOUT"), app.quit()))

app.exec()
print("TEST DONE", len(mismatches), len(progresses))
assert len(mismatches) == 1, f"expected 1 mismatch got {mismatches}"
assert len(progresses) == 2
print("PASS")
