# AutoStamper

Standalone desktop app that batch-applies a transparent PNG stamp across PDFs in a folder.

## Portable (No Install)
Office USB tool — no Python needed.
- **Single-file:** `AutoStamper.exe` (71 MB) — copy to USB, double-click. Extracts to `%TEMP%` on first run (3-4s), then runs. Single file to carry.
- **Folder:** `AutoStamper-portable/AutoStamper.exe` (170 MB folder, 76 MB ZIP) — faster start (1s), friendlier to antivirus, also portable.

Both write only `.stamped/` beside input folder, no registry/`%APPDATA%`, no admin.

```powershell
# From USB or any folder
.\AutoStamper.exe
# or
.\AutoStamper-portable\AutoStamper.exe
```

Build yourself: `pip install pyinstaller` then `.\build.ps1 -Target all` — output `dist/` (`BUILD.md` details, `AutoStamper-OneFile.spec` / `AutoStamper-Onedir.spec` lean 71 MB).

SHA256 (2026-09-23): `AutoStamper-Portable-SingleFile.zip` `E44A9B0F14A6F...B0CE0` | `AutoStamper-Portable.zip` `B8C4B69720CD...DDB8FC7`

## Stack
- Python 3.10+ (tested 3.12)
- PySide6 (Qt 6)
- PyMuPDF (`fitz`)

## Install
```bash
pip install -r requirements.txt
```

## Run
```bash
python autostamper.py
```

## Modes
* **Manual (Default)** — No standard. Step through files one by one. Click a file in the queue or use **Prev/Next**, adjust the blue box, then **Stamp & Save This File** (saves to `.stamped/` and auto-advances) or **Skip**. Ideal for mixed sizes where each page needs a tweak.
* **Automatic (Batch)** — Same as before but toggles hidden unless this mode is selected. Uses `Lock Current as Standard` + `Standard` label + **Start Batch** with pause-and-adjust on dimension mismatch (3 pt tolerance).

## How to use
1. **Pick mode** — Top of right panel: `Manual` (default) or `Automatic`.
2. **Pick folder** — Browse for folder with PDFs. Files appear in the queue as Pending.
3. **Pick stamp PNG** — Transparent PNG is recommended.
4. **Adjust stamp box** — Drag inside the canvas to move, drag handles to resize. Box shows live preview; **Lock aspect ratio** is ON by default (global, session) and forced ON while rotated to prevent shear. Position is saved as ratio to page size.
5. **Rotate** — Drag the ↻ handle above the box (center pivot) or use the Rotation slider/spinbox (0–359°). Toggle **Snap 90°** for granular (1°) vs discrete (90°) — discrete snaps handle + slider to 0/90/180/270. Rotation safest-bounds auto-fits (shift + shrink) so AABB never overflows page.
6. **Manual:** use `Prev`/`Next` or click queue, then `Stamp & Save This File` per file.
   **Automatic:** optionally **Lock Current as Standard**, then **Start Batch** — Output goes to `<input>/.stamped/<filename>` with `garbage=3, deflate=True`.

## Dimension lock
If locked and next PDF size differs by more than 3 pt in width or height, the worker pauses and you choose:
- **Apply to This File & Continue** — stamp this file with current box, keep original standard.
- **Set as New Standard & Continue** — update standard to this file’s size/box and continue.
- **Skip File** — leave file untouched.

## Project layout (modular)
```
autostamper.py              # launcher
autostamper/
  config.py                 # StampConfig dataclass + tolerance + rotation
  canvas.py                 # PDFCanvasWidget — pixmap, draggable box, rotate handle
  image.py                  # rotate helper (Pillow + AABB)
  worker.py                 # StamperWorker QThread + pause_event + rotated insert
  main_window.py            # MainWindow layout + tabbed Stamp Tools | Queue
AutoStamper-OneFile.spec    # PyInstaller single-file (71 MB)
AutoStamper-Onedir.spec     # PyInstaller onedir portable (170 MB)
build.ps1 / BUILD.md        # build docs
requirements.txt
README.md
```

Modular layout is intentional — smaller files make bug tracking and revert easier. Spec asked for a single `autostamper.py`; the launcher imports the package so you still run `python autostamper.py`.

## Code conventions
- PEP 8, type hints, minimal comments only where logic is not obvious.
- Signals: `mismatch_detected`, `progress`, `file_status`, `error`, `finished`.
- Coordinates normalized: `x_rel = x / W`, `y_rel = y / H` per spec.

## Notes
- Encrypted/corrupted PDFs are marked `Skipped` and do not stop the batch.
- `.stamped/` is created automatically with permission check.
- Only one PDF is open at a time; `doc.close()` + `del doc` each iteration — zero leak.
- Scanning is case-insensitive deduped; preview on demand via `page.get_pixmap(dpi=96)` → `QPixmap`, no doc caching.
- UI stays responsive — all I/O in `QThread`, progress via signals.
 - **Aspect lock:** ON by default (global, session) — resize handles keep proportions (`keep_proportion=True`); forced ON while rotated to prevent shear, slider/toggle disabled. Free stretch still available when not rotated by unchecking. Page switch always preserves aspect — height-anchored (`rel_h` constant, `rel_w = rel_h·aspect·H/W`) with safest-bounds shift if `rel_x+rel_w>1` (decision A).
 - **Rotation:** Center-pivot, toggle Granular (1°) vs Snap 90° discrete, draggable ↻ handle above box + slider/spinbox + ±90° buttons. Preview via `QPainter.translate→rotate`, PDF via Pillow `rotate(expand=True)` + `fitz.Pixmap(insert keep_proportion=True overlay=True)` centered on box. Overflow → safest-bounds shift + uniform shrink so rotated AABB `w' = w|c|+h|s` fits `0..1`.

## Tests
```bash
pytest -v                  # unit tests: config, canvas, modes, aspect, rotate
python tests/test_worker.py         # integration: batch with mismatch
python tests/test_worker_update.py  # integration: update/skip
```
`conftest.py` ignores legacy integration files during `pytest` collection; they run standalone.

## Commit history
Atomic commits using Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`). Small scope per commit for easy `git bisect`/`revert`.
- `chore(repo):` init + structure
- `feat(config):` StampConfig + keep_aspect
- `feat(canvas):` overlay + aspect + preview
- `feat(worker):` QThread loop
 - `feat(modes):` Manual/Automatic switch
 - `feat(rotate):` center-pivot rotate with handle, granular/discrete toggle, safest bounds + force aspect
 - `refactor(ui):` tabbed Stamp Tools | Queue — de-cluttered compact Mode/Page/Rotation
 - `feat(portable):` PyInstaller lean specs, 71 MB single-file + 170 MB onedir, zero-install office USB
 - `test(config/canvas/modes/rotate):` unit tests
 - `docs(readme):` this file
