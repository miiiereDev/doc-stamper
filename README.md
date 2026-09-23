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

## Notes
- Encrypted/corrupted PDFs are marked `Skipped` and do not stop the batch.
- `.stamped/` is created automatically.
- Only one PDF is open at a time; handles are closed right after saving.

## Commit history
Atomic commits using Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`).
