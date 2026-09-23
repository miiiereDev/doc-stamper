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

## Modes
* **Manual (Default)** — No standard. Step through files one by one. Click a file in the queue or use **Prev/Next**, adjust the blue box, then **Stamp & Save This File** (saves to `.stamped/` and auto-advances) or **Skip**. Ideal for mixed sizes where each page needs a tweak.
* **Automatic (Batch)** — Same as before but toggles hidden unless this mode is selected. Uses `Lock Current as Standard` + `Standard` label + **Start Batch** with pause-and-adjust on dimension mismatch (3 pt tolerance).

## How to use
1. **Pick mode** — Top of right panel: `Manual` (default) or `Automatic`.
2. **Pick folder** — Browse for folder with PDFs. Files appear in the queue as Pending.
3. **Pick stamp PNG** — Transparent PNG is recommended.
4. **Adjust stamp box** — Drag inside the canvas to move, drag handles to resize. Box shows live preview; toggle **Lock aspect ratio** to keep proportions (prevents warping). Position is saved as ratio to page size.
5. **Manual:** use `Prev`/`Next` or click queue, then `Stamp & Save This File` per file.
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
- **Aspect lock:** when enabled, resize handles keep stamp proportions (uses `keep_proportion=True` on insert); otherwise free stretch (`keep_proportion=False` per spec). Page switch now always preserves aspect — height-anchored (`rel_h` constant, `rel_w = rel_h·aspect·H/W`) with safest-bounds shift if `rel_x+rel_w>1`; works even when lock is OFF so selector never warps on different W×H (decision A).

## Tests
```bash
pytest -v                  # unit tests: config, canvas, modes
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
- `test(config/canvas/modes):` unit tests
- `docs(readme):` this file
