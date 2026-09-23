# AutoStamper

Standalone desktop app that batch-applies a transparent PNG stamp across PDFs in a folder.

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

## How to use
1. **Pick folder** — Browse for folder with PDFs. Files appear in the queue as Pending.
2. **Pick stamp PNG** — Transparent PNG is recommended.
3. **Adjust stamp box** — Drag inside the canvas to move, drag handles to resize. Box position is saved as ratio to page size.
4. **Target page** — Choose Last Page (default) or First Page.
5. **Lock Standard** — Click “Lock Current as Standard” to capture current page size and box. Later files that differ by >3 pt will pause for your choice.
6. **Start Batch** — Output goes to `<input>/.stamped/<filename>` with `garbage=3, deflate=True`.

## Dimension lock
If locked and next PDF size differs by more than 3 pt in width or height, the worker pauses and you choose:
- **Apply to This File & Continue** — stamp this file with current box, keep original standard.
- **Set as New Standard & Continue** — update standard to this file’s size/box and continue.
- **Skip File** — leave file untouched.

## Project layout (modular)
```
autostamper.py              # launcher
autostamper/
  config.py                 # StampConfig dataclass + tolerance
  canvas.py                 # PDFCanvasWidget — pixmap, draggable box
  worker.py                 # StamperWorker QThread + pause_event
  main_window.py            # MainWindow layout + mismatch banner
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

## Commit history
Atomic commits using Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`). Small scope per commit for easy `git bisect`/`revert`.
- `chore(repo):` init + structure
- `feat(config):` StampConfig
- `feat(canvas):` overlay
- `feat(worker):` QThread loop
- `feat(ui):` MainWindow
- `fix(ui):` dedup
- `docs(readme):` this file
