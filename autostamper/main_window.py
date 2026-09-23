import threading
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QSplitter,
    QGroupBox, QRadioButton, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QFrame, QMessageBox, QStackedWidget,
    QSlider, QSpinBox, QTabWidget
)

from .canvas import PDFCanvasWidget
from .config import StampConfig
from .worker import StamperWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoStamper")
        self.resize(1200, 800)

        self.config = StampConfig()
        self.pdf_paths: list[Path] = []
        self.worker: StamperWorker | None = None
        self.pause_event = threading.Event()
        self._mismatch_path: Path | None = None
        self._batch_aborted = False
        self.mode = "manual"
        self.manual_index = 0
        self._updating_rotation = False

        self._build_ui()
        self._connect()
        self.set_mode("manual")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        top = QGridLayout()
        top.setColumnStretch(1, 1)

        top.addWidget(QLabel("Input Folder:"), 0, 0)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Select folder with PDFs")
        self.input_edit.setReadOnly(True)
        top.addWidget(self.input_edit, 0, 1)
        self.browse_input_btn = QPushButton("Browse...")
        top.addWidget(self.browse_input_btn, 0, 2)

        top.addWidget(QLabel("Stamp PNG:"), 1, 0)
        self.stamp_edit = QLineEdit()
        self.stamp_edit.setPlaceholderText("Select transparent PNG")
        self.stamp_edit.setReadOnly(True)
        top.addWidget(self.stamp_edit, 1, 1)
        self.browse_stamp_btn = QPushButton("Browse...")
        top.addWidget(self.browse_stamp_btn, 1, 2)

        self.output_label = QLabel("Output: <not selected>/.stamped/")
        self.output_label.setStyleSheet("color: #666; font-size: 11px;")
        top.addWidget(self.output_label, 2, 0, 1, 3)

        main_layout.addLayout(top)

        self.mismatch_bar = QFrame()
        self.mismatch_bar.setStyleSheet("QFrame { background: #FFE9E9; border: 1px solid #FFB3B3; border-radius: 6px; } QLabel { border: none; }")
        self.mismatch_bar.setVisible(False)
        bar_layout = QHBoxLayout(self.mismatch_bar)
        self.mismatch_label = QLabel("Dimension Mismatch")
        self.mismatch_label.setStyleSheet("color: #900; font-weight: bold; border: none;")
        bar_layout.addWidget(self.mismatch_label)
        bar_layout.addStretch()
        self.btn_apply_once = QPushButton("Apply to This File & Continue")
        self.btn_update_std = QPushButton("Set as New Standard & Continue")
        self.btn_skip = QPushButton("Skip File")
        for b in (self.btn_apply_once, self.btn_update_std, self.btn_skip):
            b.setStyleSheet("background: white;")
        bar_layout.addWidget(self.btn_apply_once)
        bar_layout.addWidget(self.btn_update_std)
        bar_layout.addWidget(self.btn_skip)
        # abort mode — batch completely stopped, user switches to Manual
        self.btn_mismatch_close = QPushButton("Dismiss — Switch to Manual")
        self.btn_mismatch_close.setStyleSheet("background: white; font-weight: bold;")
        self.btn_mismatch_close.setVisible(False)
        bar_layout.addWidget(self.btn_mismatch_close)
        main_layout.addWidget(self.mismatch_bar)

        splitter = QSplitter(Qt.Horizontal)

        self.canvas = PDFCanvasWidget(self.config)
        splitter.addWidget(self.canvas)

        right = QWidget()
        right.setMinimumWidth(360)
        right.setMaximumWidth(440)
        r_layout = QVBoxLayout(right)
        r_layout.setContentsMargins(6, 6, 6, 6)
        r_layout.setSpacing(6)

        # Tabbed right panel — Option A
        self.right_tabs = QTabWidget()
        self.right_tabs.setTabPosition(QTabWidget.North)

        # Stamp Tools tab
        stamp_tab = QWidget()
        s_layout = QVBoxLayout(stamp_tab)
        s_layout.setContentsMargins(6, 6, 6, 6)
        s_layout.setSpacing(8)

        # Mode + Target Page compact bar
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(QLabel("Mode:"))
        self.radio_manual = QRadioButton("Manual")
        self.radio_auto = QRadioButton("Automatic")
        self.radio_manual.setChecked(True)
        self.radio_manual.setToolTip("One by one (Default)")
        self.radio_auto.setToolTip("Batch with Standard")
        mode_row.addWidget(self.radio_manual)
        mode_row.addWidget(self.radio_auto)
        mode_row.addStretch()
        s_layout.addLayout(mode_row)

        page_row = QHBoxLayout()
        page_row.setSpacing(8)
        page_row.addWidget(QLabel("Page:"))
        self.radio_last = QRadioButton("Last")
        self.radio_first = QRadioButton("First")
        self.radio_last.setChecked(True)
        page_row.addWidget(self.radio_last)
        page_row.addWidget(self.radio_first)
        page_row.addStretch()
        self.aspect_check = QCheckBox("Lock aspect")
        self.aspect_check.setToolTip("Prevent stamp from stretching — keep original proportions")
        self.aspect_check.setChecked(self.config.keep_aspect)
        page_row.addWidget(self.aspect_check)
        s_layout.addLayout(page_row)

        # rotation group — compact single group, hint as tooltip
        rot_grp = QGroupBox("Rotation  — drag ↻ handle (center pivot)")
        rot_grp.setToolTip("Drag the ↻ handle above the box or use slider. Granular 1° vs Snap 90° discrete.")
        rot_layout = QVBoxLayout(rot_grp)
        rot_layout.setContentsMargins(6, 6, 6, 6)
        rot_layout.setSpacing(6)
        slider_row = QHBoxLayout()
        self.rotation_slider = QSlider(Qt.Horizontal)
        self.rotation_slider.setRange(0, 359)
        self.rotation_slider.setValue(int(self.config.rotation))
        self.rotation_slider.setTickPosition(QSlider.TicksBelow)
        self.rotation_slider.setTickInterval(45)
        self.rotation_slider.setSingleStep(1)
        slider_row.addWidget(self.rotation_slider, 1)
        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(0, 359)
        self.rotation_spin.setSuffix("°")
        self.rotation_spin.setValue(int(self.config.rotation))
        self.rotation_spin.setFixedWidth(68)
        slider_row.addWidget(self.rotation_spin)
        rot_layout.addLayout(slider_row)
        snap_row = QHBoxLayout()
        self.snap_check = QCheckBox("Snap 90°")
        self.snap_check.setChecked(self.config.rotation_snap_90)
        self.snap_check.setToolTip("Toggle Granular 1° vs Discrete 90° steps. Handle drag also snaps.")
        snap_row.addWidget(self.snap_check)
        snap_row.addStretch()
        self.btn_rot_ccw = QPushButton("↺ 90°")
        self.btn_rot_ccw.setFixedWidth(56)
        self.btn_rot_cw = QPushButton("↻ 90°")
        self.btn_rot_cw.setFixedWidth(56)
        snap_row.addWidget(self.btn_rot_ccw)
        snap_row.addWidget(self.btn_rot_cw)
        rot_layout.addLayout(snap_row)
        s_layout.addWidget(rot_grp)
        self._sync_rotation_ui()

        self.stack = QStackedWidget()
        # manual panel
        manual_page = QWidget()
        mp_layout = QVBoxLayout(manual_page)
        mp_layout.setContentsMargins(0, 0, 0, 0)
        mp_layout.setSpacing(6)
        self.manual_info = QLabel("No files")
        self.manual_info.setStyleSheet("color: #333; font-weight: bold;")
        self.manual_info.setWordWrap(True)
        mp_layout.addWidget(self.manual_info)
        nav = QHBoxLayout()
        self.manual_prev = QPushButton("◀ Prev")
        self.manual_next = QPushButton("Next ▶")
        nav.addWidget(self.manual_prev)
        nav.addWidget(self.manual_next)
        mp_layout.addLayout(nav)
        self.manual_stamp_btn = QPushButton("Stamp & Save This File")
        self.manual_stamp_btn.setMinimumHeight(34)
        self.manual_stamp_btn.setStyleSheet("QPushButton { background: #34c759; color: white; font-weight: bold; border-radius: 6px; } QPushButton:disabled { background: #aaa; }")
        mp_layout.addWidget(self.manual_stamp_btn)
        self.manual_skip_btn = QPushButton("Skip This File")
        mp_layout.addWidget(self.manual_skip_btn)
        mp_layout.addStretch()
        self.stack.addWidget(manual_page)

        # auto panel
        auto_page = QWidget()
        ap_layout = QVBoxLayout(auto_page)
        ap_layout.setContentsMargins(0, 0, 0, 0)
        ap_layout.setSpacing(6)
        self.lock_btn = QPushButton("Lock Current as Standard")
        self.lock_btn.setCheckable(True)
        ap_layout.addWidget(self.lock_btn)
        self.standard_label = QLabel(self.config.label())
        self.standard_label.setStyleSheet("color: #333; font-size: 12px;")
        self.standard_label.setWordWrap(True)
        ap_layout.addWidget(self.standard_label)
        self.aspect_halt_check = QCheckBox("Halt on aspect change (20%)")
        self.aspect_halt_check.setChecked(self.config.halt_on_aspect_mismatch)
        self.aspect_halt_check.setToolTip("Stop batch if aspect W/H differs >20% from Standard — prevents warped stamps. ON by default, works regardless of lock when Standard exists.")
        ap_layout.addWidget(self.aspect_halt_check)
        self.auto_skip_check = QCheckBox("Auto-skip mismatches")
        self.auto_skip_check.setChecked(self.config.auto_skip_mismatches)
        self.auto_skip_check.setToolTip("When ON, mismatched files are automatically skipped and left as Mismatch for manual review — batch does not abort; you can filter Queue to review only mismatches.")
        ap_layout.addWidget(self.auto_skip_check)
        self.start_btn = QPushButton("Start Batch")
        self.start_btn.setEnabled(False)
        self.start_btn.setMinimumHeight(36)
        self.start_btn.setStyleSheet("QPushButton { background: #0a84ff; color: white; font-weight: bold; border-radius: 6px; } QPushButton:disabled { background: #aaa; }")
        ap_layout.addWidget(self.start_btn)
        ap_layout.addStretch()
        self.stack.addWidget(auto_page)

        s_layout.addWidget(self.stack)
        s_layout.addStretch()

        self.right_tabs.addTab(stamp_tab, "Stamp Tools")

        # Queue tab — full-height table
        queue_tab = QWidget()
        q_layout = QVBoxLayout(queue_tab)
        q_layout.setContentsMargins(6, 6, 6, 6)
        q_layout.setSpacing(6)
        self.queue_count = QLabel("No files")
        self.queue_count.setStyleSheet("color: #888; font-size: 11px;")
        q_layout.addWidget(self.queue_count)
        filter_row = QHBoxLayout()
        self.mismatch_filter_check = QCheckBox("Show only mismatches")
        self.mismatch_filter_check.setToolTip("Filter Queue to show only Mismatch files for manual editing")
        filter_row.addWidget(self.mismatch_filter_check)
        filter_row.addStretch()
        self.btn_review_mismatches = QPushButton("Review mismatches → Manual")
        self.btn_review_mismatches.setToolTip("Switch to Manual and show only mismatched files for editing")
        self.btn_review_mismatches.setStyleSheet("background: #FFE9E9; font-weight: bold;")
        self.btn_review_mismatches.setEnabled(False)
        filter_row.addWidget(self.btn_review_mismatches)
        q_layout.addLayout(filter_row)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Filename", "Status", "Dimensions"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        q_layout.addWidget(self.table)

        self.right_tabs.addTab(queue_tab, "Queue")

        r_layout.addWidget(self.right_tabs, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        bottom.addWidget(self.progress, 1)
        self.status_label = QLabel("Idle — select input folder and stamp PNG")
        self.status_label.setStyleSheet("color: #555; font-size: 11px;")
        bottom.addWidget(self.status_label, 2)
        main_layout.addLayout(bottom)

    def set_mode(self, mode: str):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Busy", "Cannot switch mode while batch is running")
            self.radio_manual.setChecked(mode == "manual")
            self.radio_auto.setChecked(mode == "auto")
            return
        self.mode = mode
        is_manual = mode == "manual"
        self.stack.setCurrentIndex(0 if is_manual else 1)
        self.mismatch_bar.setVisible(False)
        self.update_manual_ui()
        self.validate_start()
        self.status_label.setText(f"Mode: {'Manual' if is_manual else 'Automatic'} — {'step through files' if is_manual else 'batch with standard'}")

    def on_mode_changed(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Busy", "Cannot switch mode while batch is running")
            # revert radios will be handled by set_mode guard
            return
        if self.radio_manual.isChecked():
            self.set_mode("manual")
        else:
            self.set_mode("auto")

    def update_manual_ui(self):
        total = len(self.pdf_paths)
        mismatch_rows = self._mismatch_rows() if hasattr(self, "_mismatch_rows") else []
        if hasattr(self, "queue_count"):
            pending = sum(1 for r in range(self.table.rowCount()) if (self.table.item(r, 1) and self.table.item(r, 1).text() == "Pending"))
            done = sum(1 for r in range(self.table.rowCount()) if (self.table.item(r, 1) and self.table.item(r, 1).text() == "Done"))
            mismatch = len(mismatch_rows)
            if mismatch:
                self.queue_count.setText(f"{total} files — {pending} pending, {done} done, {mismatch} mismatch")
            else:
                self.queue_count.setText(f"{total} files — {pending} pending, {done} done")
            try:
                self.right_tabs.setTabText(1, f"Queue ({total})")
            except Exception:
                pass
        if hasattr(self, "_update_review_button"):
            self._update_review_button()
        if total == 0:
            self.manual_info.setText("No files")
            self.manual_prev.setEnabled(False)
            self.manual_next.setEnabled(False)
            self.manual_stamp_btn.setEnabled(False)
            self.manual_skip_btn.setEnabled(False)
            return
        self.manual_index = max(0, min(self.manual_index, total - 1))
        # if filter active and current row is hidden, jump to next visible mismatch
        if hasattr(self, "mismatch_filter_check") and self.mismatch_filter_check.isChecked():
            if self.table.isRowHidden(self.manual_index):
                rows = self._mismatch_rows()
                if rows:
                    # find closest visible
                    nxt = next((r for r in rows if r > self.manual_index), rows[0])
                    self.manual_index = nxt
        cur = self.pdf_paths[self.manual_index]
        status = self.table.item(self.manual_index, 1).text() if self.table.item(self.manual_index, 1) else "Pending"
        # show filtered position when filter active
        if hasattr(self, "mismatch_filter_check") and self.mismatch_filter_check.isChecked() and self._is_mismatch_status(status):
            rows = self._mismatch_rows()
            pos = rows.index(self.manual_index) + 1 if self.manual_index in rows else 1
            self.manual_info.setText(f"Mismatch {pos} of {len(rows)}: {cur.name} ({status}) — filtered")
        else:
            self.manual_info.setText(f"File {self.manual_index + 1} of {total}: {cur.name} ({status})")
        # Prev/Next respect filter
        if hasattr(self, "mismatch_filter_check") and self.mismatch_filter_check.isChecked():
            rows = self._mismatch_rows()
            if not rows:
                self.manual_prev.setEnabled(False)
                self.manual_next.setEnabled(False)
            else:
                idx = rows.index(self.manual_index) if self.manual_index in rows else 0
                self.manual_prev.setEnabled(idx > 0)
                self.manual_next.setEnabled(idx < len(rows) - 1)
        else:
            self.manual_prev.setEnabled(self.manual_index > 0)
            self.manual_next.setEnabled(self.manual_index < total - 1)
        has_stamp = bool(self.stamp_edit.text() and Path(self.stamp_edit.text()).exists())
        self.manual_stamp_btn.setEnabled(has_stamp and status not in ("Done",))
        self.manual_skip_btn.setEnabled(status not in ("Done", "Skipped"))
        self.progress.setValue(int((self.manual_index / max(1, total)) * 100))

    def _find_next_mismatch(self, start: int, direction: int) -> int | None:
        rows = self._mismatch_rows()
        if not rows:
            return None
        if direction > 0:
            nxt = [r for r in rows if r > start]
            return nxt[0] if nxt else None
        else:
            prev = [r for r in rows if r < start]
            return prev[-1] if prev else None

    def manual_prev_file(self):
        if hasattr(self, "mismatch_filter_check") and self.mismatch_filter_check.isChecked():
            nxt = self._find_next_mismatch(self.manual_index, -1)
            if nxt is not None:
                self.manual_index = nxt
                self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
                self.table.selectRow(self.manual_index)
                self.update_manual_ui()
                return
        if self.manual_index > 0:
            self.manual_index -= 1
            self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
            self.table.selectRow(self.manual_index)
            self.update_manual_ui()

    def manual_next_file(self):
        if hasattr(self, "mismatch_filter_check") and self.mismatch_filter_check.isChecked():
            nxt = self._find_next_mismatch(self.manual_index, 1)
            if nxt is not None:
                self.manual_index = nxt
                self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
                self.table.selectRow(self.manual_index)
                self.update_manual_ui()
                return
        if self.manual_index < len(self.pdf_paths) - 1:
            self.manual_index += 1
            self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
            self.table.selectRow(self.manual_index)
            self.update_manual_ui()

    def manual_skip_current(self):
        if not self.pdf_paths:
            return
        self.table.setItem(self.manual_index, 1, QTableWidgetItem("Skipped"))
        # if filter active, directly hide Skipped row (no longer mismatch) without auto-jump side effect
        if hasattr(self, "mismatch_filter_check") and self.mismatch_filter_check.isChecked():
            # Skipped is not a mismatch, so hide this row
            self.table.setRowHidden(self.manual_index, True)
            self._update_review_button()
            if self.table.isRowHidden(self.manual_index):
                rows = self._mismatch_rows()
                if rows:
                    nxt = next((r for r in rows if r > self.manual_index), rows[0])
                    self.manual_index = nxt
                    self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
                    self.table.selectRow(self.manual_index)
                    self.update_manual_ui()
                    return
                else:
                    self.mismatch_filter_check.setChecked(False)
                    self.status_label.setText("All mismatches resolved — filter cleared")
        self.update_manual_ui()
        if self.manual_index < len(self.pdf_paths) - 1:
            # respect filter
            if hasattr(self, "mismatch_filter_check") and self.mismatch_filter_check.isChecked():
                nxt = self._find_next_mismatch(self.manual_index, 1)
                if nxt is not None:
                    self.manual_index = nxt
                    self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
                    self.table.selectRow(self.manual_index)
                    self.update_manual_ui()
                    return
            self.manual_next_file()
        else:
            self.status_label.setText("Manual: skipped last file")

    def manual_stamp_current(self):
        if not self.pdf_paths:
            return
        stamp_path = Path(self.stamp_edit.text())
        if not stamp_path.exists():
            QMessageBox.warning(self, "Missing", "Stamp PNG not found")
            return
        pdf_path = self.pdf_paths[self.manual_index]
        input_dir = Path(self.input_edit.text())
        if not input_dir.exists():
            QMessageBox.warning(self, "Missing", "Input folder not found")
            return
        out_dir = input_dir / ".stamped"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            QMessageBox.warning(self, "Error", f"Cannot create output: {e}")
            return
        try:
            doc = __import__("fitz").open(str(pdf_path))
        except Exception as e:
            self.table.setItem(self.manual_index, 1, QTableWidgetItem("Skipped (Corrupted)"))
            self.status_label.setText(f"Corrupted {pdf_path.name}: {e}")
            self.update_manual_ui()
            return
        if doc.is_encrypted:
            doc.close()
            self.table.setItem(self.manual_index, 1, QTableWidgetItem("Skipped (Encrypted)"))
            self.update_manual_ui()
            return
        page_idx = 0 if self.config.target_page == "first" else len(doc) - 1
        page = doc[page_idx]
        W = float(page.rect.width)
        H = float(page.rect.height)
        rect = __import__("fitz").Rect(
            self.config.rel_x * W,
            self.config.rel_y * H,
            (self.config.rel_x + self.config.rel_w) * W,
            (self.config.rel_y + self.config.rel_h) * H,
        )
        try:
            if self.config.rotation % 360 != 0:
                from .image import prepare_stamp_bytes
                data = prepare_stamp_bytes(stamp_path, self.config.rotation)
                if data:
                    pix = __import__("fitz").Pixmap(data)
                    page.insert_image(rect, pixmap=pix, keep_proportion=True, overlay=True)
                else:
                    page.insert_image(rect, filename=str(stamp_path), keep_proportion=True)
            else:
                page.insert_image(rect, filename=str(stamp_path), keep_proportion=self.config.keep_aspect)
        except Exception as e:
            doc.close()
            self.table.setItem(self.manual_index, 1, QTableWidgetItem("Skipped (Stamp Error)"))
            self.status_label.setText(f"Stamp error {pdf_path.name}: {e}")
            self.update_manual_ui()
            return
        out_path = out_dir / pdf_path.name
        try:
            doc.save(str(out_path), garbage=3, deflate=True)
        except Exception as e:
            doc.close()
            self.table.setItem(self.manual_index, 1, QTableWidgetItem("Skipped (Save Error)"))
            self.status_label.setText(f"Save error {pdf_path.name}: {e}")
            self.update_manual_ui()
            return
        doc.close()
        self.table.setItem(self.manual_index, 1, QTableWidgetItem("Done"))
        self.status_label.setText(f"Stamped {pdf_path.name} → {out_path}")
        # if filter active, hide this Done row and jump to next mismatch (avoid double-jump via apply_mismatch_filter auto-jump)
        if hasattr(self, "mismatch_filter_check") and self.mismatch_filter_check.isChecked():
            # directly hide the just-Done row instead of re-applying full filter which jumps to first mismatch
            self.table.setRowHidden(self.manual_index, True)
            self._update_review_button()
            if self.table.isRowHidden(self.manual_index):
                rows = self._mismatch_rows()
                if rows:
                    nxt = next((r for r in rows if r > self.manual_index), None)
                    if nxt is not None:
                        self.manual_index = nxt
                    else:
                        # wrapped to first remaining mismatch
                        self.manual_index = rows[0]
                    self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
                    self.table.selectRow(self.manual_index)
                    self.update_manual_ui()
                    return
                else:
                    self.mismatch_filter_check.setChecked(False)
                    self.status_label.setText("All mismatches resolved — filter cleared, showing all files")
        self.update_manual_ui()
        if self.manual_index < len(self.pdf_paths) - 1:
            # respect filter for next
            if hasattr(self, "mismatch_filter_check") and self.mismatch_filter_check.isChecked():
                nxt = self._find_next_mismatch(self.manual_index, 1)
                if nxt is not None:
                    self.manual_index = nxt
                    self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
                    self.table.selectRow(self.manual_index)
                    self.update_manual_ui()
                    return
            self.manual_next_file()
        else:
            self.progress.setValue(100)
            self.status_label.setText(f"Manual done — {len(self.pdf_paths)} files")

    def _sync_rotation_ui(self):
        self._updating_rotation = True
        try:
            v = int(round(self.config.rotation)) % 360
            self.rotation_slider.setValue(v)
            self.rotation_spin.setValue(v)
            self.snap_check.setChecked(self.config.rotation_snap_90)
            if self.config.rotation_snap_90:
                self.rotation_slider.setSingleStep(90)
                self.rotation_slider.setTickInterval(90)
                self.rotation_spin.setSingleStep(90)
            else:
                self.rotation_slider.setSingleStep(1)
                self.rotation_slider.setTickInterval(45)
                self.rotation_spin.setSingleStep(1)
            # force keep_aspect when rotated
            if self.config.rotation % 360 != 0:
                if not self.config.keep_aspect:
                    self.config.keep_aspect = True
                self.aspect_check.setChecked(True)
                self.aspect_check.setEnabled(False)
                self.aspect_check.setToolTip("Forced ON while rotated — prevents shear")
            else:
                self.aspect_check.setEnabled(True)
                self.aspect_check.setToolTip("Prevent stamp from stretching — keep original image proportions")
        finally:
            self._updating_rotation = False

    def _apply_rotation(self, value: float):
        if self._updating_rotation:
            return
        v = float(value) % 360
        if self.config.rotation_snap_90:
            v = round(v / 90) * 90 % 360
        self.config.rotation = v
        if v % 360 != 0 and not self.config.keep_aspect:
            self.config.keep_aspect = True
        self.canvas.set_config(self.config)
        self._sync_rotation_ui()
        self.canvas.update()
        self.status_label.setText(f"Rotation {v:.0f}° — {'Discrete 90°' if self.config.rotation_snap_90 else 'Granular 1°'} — drag ↻ handle or slider")

    def on_rotation_slider(self, v: int):
        if self._updating_rotation:
            return
        self._apply_rotation(float(v))
        # sync spin without recursion
        self._updating_rotation = True
        self.rotation_spin.setValue(int(round(self.config.rotation)) % 360)
        self._updating_rotation = False

    def on_rotation_spin(self, v: int):
        if self._updating_rotation:
            return
        self._apply_rotation(float(v))
        self._updating_rotation = True
        self.rotation_slider.setValue(int(round(self.config.rotation)) % 360)
        self._updating_rotation = False

    def on_snap_toggled(self, checked: bool):
        self.config.rotation_snap_90 = bool(checked)
        # snap current rotation
        self.config.normalize_rotation()
        if self.config.rotation % 360 != 0 and not self.config.keep_aspect:
            self.config.keep_aspect = True
        self.canvas.set_config(self.config)
        self._sync_rotation_ui()
        self.status_label.setText(f"Rotation mode {'Discrete 90°' if checked else 'Granular 1°'} — {self.config.rotation:.0f}°")

    def nudge_rotation(self, delta: float):
        new_v = (self.config.rotation + delta) % 360
        if self.config.rotation_snap_90:
            new_v = round(new_v / 90) * 90 % 360
        self._apply_rotation(new_v)
        self._updating_rotation = True
        self.rotation_slider.setValue(int(round(self.config.rotation)) % 360)
        self.rotation_spin.setValue(int(round(self.config.rotation)) % 360)
        self._updating_rotation = False

    def _stamped_names(self, folder: Path) -> set[str]:
        stamped = folder / ".stamped"
        if not stamped.exists():
            return set()
        return {p.name for p in list(stamped.glob("*.pdf")) + list(stamped.glob("*.PDF"))}

    def _connect(self):
        self.browse_input_btn.clicked.connect(self.pick_input)
        self.browse_stamp_btn.clicked.connect(self.pick_stamp)
        self.radio_last.toggled.connect(self.on_target_changed)
        self.radio_manual.toggled.connect(self.on_mode_changed)
        self.lock_btn.clicked.connect(self.on_lock)
        self.aspect_check.toggled.connect(self.on_aspect_toggled)
        self.aspect_halt_check.toggled.connect(self.on_aspect_halt_toggled)
        self.auto_skip_check.toggled.connect(self.on_auto_skip_toggled)
        self.mismatch_filter_check.toggled.connect(self.apply_mismatch_filter)
        self.btn_review_mismatches.clicked.connect(self.review_mismatches)
        self.rotation_slider.valueChanged.connect(self.on_rotation_slider)
        self.rotation_spin.valueChanged.connect(self.on_rotation_spin)
        self.snap_check.toggled.connect(self.on_snap_toggled)
        self.btn_rot_ccw.clicked.connect(lambda: self.nudge_rotation(-90))
        self.btn_rot_cw.clicked.connect(lambda: self.nudge_rotation(90))
        self.canvas.config_changed.connect(self.on_canvas_config)
        self.start_btn.clicked.connect(self.start_batch)
        self.manual_prev.clicked.connect(self.manual_prev_file)
        self.manual_next.clicked.connect(self.manual_next_file)
        self.manual_stamp_btn.clicked.connect(self.manual_stamp_current)
        self.manual_skip_btn.clicked.connect(self.manual_skip_current)
        self.btn_apply_once.clicked.connect(self.on_apply_once)
        self.btn_update_std.clicked.connect(self.on_update_std)
        self.btn_skip.clicked.connect(self.on_skip)
        self.btn_mismatch_close.clicked.connect(self.on_mismatch_close)
        self.table.cellClicked.connect(self.on_table_click)

    def pick_input(self):
        d = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if not d:
            return
        p = Path(d)
        self.input_edit.setText(str(p))
        self.output_label.setText(f"Output: {p / '.stamped'}/")
        self.scan_pdfs(p)

    def pick_stamp(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Stamp PNG", "", "PNG (*.png);;All (*)")
        if not f:
            return
        self.stamp_edit.setText(f)
        self.canvas.set_stamp(f)
        self.validate_start()

    def scan_pdfs(self, folder: Path):
        found = {p.resolve(): p for p in list(folder.glob("*.pdf")) + list(folder.glob("*.PDF"))}
        self.pdf_paths = sorted(found.values())
        self.manual_index = 0
        self.table.setRowCount(0)
        stamped_names = self._stamped_names(folder)
        for pdf in self.pdf_paths:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(pdf.name))
            # already-done comparison: mark as Skipped (Already Done) but keep in table, Auto will skip via worker guard
            if pdf.name in stamped_names:
                self.table.setItem(row, 1, QTableWidgetItem("Skipped (Already Done)"))
            else:
                self.table.setItem(row, 1, QTableWidgetItem("Pending"))
            self.table.setItem(row, 2, QTableWidgetItem(""))
            self.table.item(row, 0).setData(Qt.UserRole, str(pdf))

        if self.pdf_paths:
            self.canvas.load_pdf(self.pdf_paths[0], self.config.target_page)
            self.status_label.setText(f"Found {len(self.pdf_paths)} PDFs — adjust stamp box then Start")
        else:
            self.canvas.clear()
            self.status_label.setText("No PDFs found in selected folder")

        if self.config.is_locked:
            self.config.is_locked = False
            self.lock_btn.setChecked(False)
            self.lock_btn.setText("Lock Current as Standard")
            self.standard_label.setText(self.config.label())

        # reset filter on new scan
        if hasattr(self, "mismatch_filter_check"):
            self.mismatch_filter_check.blockSignals(True)
            self.mismatch_filter_check.setChecked(False)
            self.mismatch_filter_check.blockSignals(False)
            for r in range(self.table.rowCount()):
                self.table.setRowHidden(r, False)

        self.update_manual_ui()
        self.validate_start()

    def on_target_changed(self):
        self.config.target_page = "first" if self.radio_first.isChecked() else "last"
        if self.pdf_paths:
            idx = self.manual_index if self.mode == "manual" else 0
            idx = max(0, min(idx, len(self.pdf_paths) - 1))
            self.canvas.load_pdf(self.pdf_paths[idx], self.config.target_page)
            self.standard_label.setText(self.config.label())

    def on_lock(self, checked: bool):
        if checked:
            if not self.canvas._pixmap:
                QMessageBox.warning(self, "No preview", "Load a PDF first before locking standard.")
                self.lock_btn.setChecked(False)
                return
            self.config.std_width = self.canvas._page_w
            self.config.std_height = self.canvas._page_h
            self.config.is_locked = True
            self.lock_btn.setText("Unlock Standard")
        else:
            self.config.is_locked = False
            self.lock_btn.setText("Lock Current as Standard")
        self.standard_label.setText(self.config.label())
        self.canvas.set_config(self.config)

    def on_aspect_toggled(self, checked: bool):
        # force ON while rotated
        if self.config.rotation % 360 != 0 and not checked:
            self.aspect_check.setChecked(True)
            self.status_label.setText("Aspect forced ON while rotated — prevents shear")
            return
        self.config.keep_aspect = checked
        if checked and self.canvas._stamp_pixmap and not self.canvas._stamp_pixmap.isNull():
            aspect = self.canvas._stamp_pixmap.width() / max(1, self.canvas._stamp_pixmap.height())
            W = self.canvas._page_w or 612
            H = self.canvas._page_h or 792
            cur_pdf_aspect = (self.config.rel_w * W) / max(0.001, self.config.rel_h * H)
            if abs(cur_pdf_aspect - aspect) > 0.01:
                new_h = self.config.rel_w * W / (aspect * H)
                if self.config.rel_y + new_h <= 1.0 and new_h > 0.02:
                    self.config.rel_h = new_h
                else:
                    new_w = self.config.rel_h * aspect * H / W
                    if self.config.rel_x + new_w <= 1.0:
                        self.config.rel_w = new_w
                self.canvas.set_config(self.config)
        self.canvas.update()
        self.status_label.setText(f"Aspect lock {'ON' if checked else 'OFF'} — {'proportions kept' if checked else 'free stretch'}")

    def on_aspect_halt_toggled(self, checked: bool):
        self.config.halt_on_aspect_mismatch = bool(checked)
        self.status_label.setText(f"Aspect halt {'ON (20%)' if checked else 'OFF'} — {'stops on W/H change' if checked else 'ignore aspect changes'}")

    def on_auto_skip_toggled(self, checked: bool):
        self.config.auto_skip_mismatches = bool(checked)
        mode = "auto-skip ON — mismatches will be left for manual review" if checked else "auto-skip OFF — mismatches abort batch"
        self.status_label.setText(f"Auto-skip {mode}")

    def _is_mismatch_status(self, status: str) -> bool:
        return status in ("Mismatch", "Aspect Mismatch", "Mismatch (Aspect+Size)")

    def _mismatch_rows(self) -> list[int]:
        rows = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            if item and self._is_mismatch_status(item.text()):
                rows.append(r)
        return rows

    def _update_review_button(self):
        has_mismatch = len(self._mismatch_rows()) > 0
        if hasattr(self, "btn_review_mismatches"):
            self.btn_review_mismatches.setEnabled(has_mismatch)
            if has_mismatch:
                self.btn_review_mismatches.setText(f"Review {len(self._mismatch_rows())} mismatches → Manual")
            else:
                self.btn_review_mismatches.setText("Review mismatches → Manual")

    def apply_mismatch_filter(self, enabled: bool):
        mismatch_count = 0
        visible_count = 0
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            status = item.text() if item else ""
            is_mismatch = self._is_mismatch_status(status)
            if is_mismatch:
                mismatch_count += 1
            hidden = enabled and not is_mismatch
            self.table.setRowHidden(r, hidden)
            if not hidden:
                visible_count += 1
        if enabled:
            self.status_label.setText(f"Filtered — showing {mismatch_count} mismatches out of {self.table.rowCount()} files — Manual editing only mismatches")
            # if in manual mode, jump to first mismatch
            if self.mode == "manual" and mismatch_count > 0:
                rows = self._mismatch_rows()
                if rows:
                    self.manual_index = rows[0]
                    self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
                    self.table.selectRow(self.manual_index)
        else:
            self.status_label.setText(f"Filter cleared — showing all {self.table.rowCount()} files")
        self.update_manual_ui()

    def review_mismatches(self):
        rows = self._mismatch_rows()
        if not rows:
            QMessageBox.information(self, "No mismatches", "No mismatched files to review.")
            return
        # switch to manual and filter
        self.set_mode("manual")
        self.mismatch_filter_check.setChecked(True)
        # apply_mismatch_filter will be triggered via toggled signal, but ensure
        self.apply_mismatch_filter(True)
        self.manual_index = rows[0]
        self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
        self.table.selectRow(self.manual_index)
        self.update_manual_ui()
        self.status_label.setText(f"Reviewing {len(rows)} mismatches — use Prev/Next to step through mismatches only")

    def on_canvas_config(self, cfg):
        self.config = cfg
        self.config.normalize_rotation()
        # force keep_aspect while rotated
        if self.config.rotation % 360 != 0 and not self.config.keep_aspect:
            self.config.keep_aspect = True
        self.aspect_check.setChecked(self.config.keep_aspect)
        if self.config.rotation % 360 != 0:
            self.aspect_check.setEnabled(False)
            self.aspect_check.setToolTip("Forced ON while rotated — prevents shear")
        else:
            self.aspect_check.setEnabled(True)
            self.aspect_check.setToolTip("Prevent stamp from stretching — keep original image proportions")
        self._sync_rotation_ui()
        if self.config.is_locked:
            self.standard_label.setText(self.config.label())

    def validate_start(self):
        has_input = bool(self.input_edit.text() and self.pdf_paths)
        has_stamp = bool(self.stamp_edit.text() and Path(self.stamp_edit.text()).exists())
        self.start_btn.setEnabled(has_input and has_stamp and self.worker is None and self.mode == "auto")
        self.update_manual_ui()

    def on_table_click(self, row, _col):
        item = self.table.item(row, 0)
        if not item:
            return
        path = Path(str(item.data(Qt.UserRole)))
        if path.exists():
            self.canvas.load_pdf(path, self.config.target_page)
            if self.mode == "manual":
                self.manual_index = row
                self.update_manual_ui()

    def start_batch(self):
        input_dir = Path(self.input_edit.text())
        stamp_path = Path(self.stamp_edit.text())
        if not input_dir.exists():
            QMessageBox.warning(self, "Missing", "Input folder not found")
            return
        if not stamp_path.exists():
            QMessageBox.warning(self, "Missing", "Stamp PNG not found")
            return
        if not self.pdf_paths:
            QMessageBox.information(self, "Empty", "No PDFs to process")
            return

        self.progress.setValue(0)
        self.status_label.setText(f"Processed 0 of {len(self.pdf_paths)} | Starting...")
        # preserve Already Done marks, refresh from .stamped vs root comparison per-file
        stamped = self._stamped_names(input_dir)
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            cur = self.table.item(r, 1).text() if self.table.item(r, 1) else "Pending"
            if item and item.text() in stamped:
                self.table.setItem(r, 1, QTableWidgetItem("Skipped (Already Done)"))
            elif cur == "Skipped (Already Done)":
                # was marked done but now removed from .stamped -> reset
                self.table.setItem(r, 1, QTableWidgetItem("Pending"))
            else:
                self.table.setItem(r, 1, QTableWidgetItem("Pending"))

        self.start_btn.setEnabled(False)
        self.browse_input_btn.setEnabled(False)
        self.browse_stamp_btn.setEnabled(False)

        self._batch_aborted = False
        # clear mismatch filter during batch so all progress visible
        if hasattr(self, "mismatch_filter_check") and self.mismatch_filter_check.isChecked():
            self.mismatch_filter_check.blockSignals(True)
            self.mismatch_filter_check.setChecked(False)
            self.mismatch_filter_check.blockSignals(False)
            for r in range(self.table.rowCount()):
                self.table.setRowHidden(r, False)
        self.btn_review_mismatches.setStyleSheet("background: #FFE9E9; font-weight: bold;")
        self.pause_event = threading.Event()
        self.worker = StamperWorker(self.pdf_paths, stamp_path, self.config, self.pause_event, input_dir)
        self.worker.mismatch_detected.connect(self.on_mismatch)
        self.worker.progress.connect(self.on_progress)
        self.worker.file_status.connect(self.on_file_status)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_mismatch(self, path_str: str, page_idx: int, w: float, h: float):
        # auto-skip mode — don't abort, just leave Mismatch for manual review
        if self.config.auto_skip_mismatches:
            cur_aspect = w / h if h else 0
            std_aspect = self.config.std_aspect
            aspect_info = ""
            if std_aspect:
                diff_pct = abs(cur_aspect / std_aspect - 1) * 100 if std_aspect else 0
                aspect_info = f" | Aspect {cur_aspect:.3f} ({diff_pct:.1f}% off)"
            self.status_label.setText(f"Auto-skipped mismatch {Path(path_str).name} ({w:.1f} x {h:.1f} pt){aspect_info} — queued for manual review")
            self._update_review_button()
            return
        self._mismatch_path = Path(path_str)
        self._batch_aborted = True
        cur_aspect = w / h if h else 0
        std_aspect = self.config.std_aspect
        aspect_info = ""
        if std_aspect and self.config.halt_on_aspect_mismatch:
            diff_pct = abs(cur_aspect / std_aspect - 1) * 100 if std_aspect else 0
            # show aspect detail when relevant
            if self.config.violates_aspect(w, h) or diff_pct > 0.5:
                aspect_info = f" | Aspect {cur_aspect:.3f} vs std {std_aspect:.3f} ({diff_pct:.1f}% off)"
        self.mismatch_label.setText(f"Batch STOPPED — Aspect Mismatch: {self._mismatch_path.name} ({w:.1f} x {h:.1f} pt){aspect_info} — switch to Manual to review")
        self.mismatch_bar.setVisible(True)
        # abort mode: hide continue buttons, show dismiss->Manual
        self.btn_apply_once.setVisible(False)
        self.btn_update_std.setVisible(False)
        self.btn_skip.setVisible(False)
        self.btn_mismatch_close.setVisible(True)
        self.canvas.load_pdf(self._mismatch_path, self.config.target_page)
        self.status_label.setText(f"STOPPED — mismatch {self._mismatch_path.name} ({w:.1f} x {h:.1f} pt){aspect_info} — batch aborted, switch to Manual")

    def on_file_status(self, path_str: str, status: str):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.data(Qt.UserRole) == path_str:
                self.table.setItem(r, 1, QTableWidgetItem(status))
                if status in ("Mismatch", "Aspect Mismatch", "Mismatch (Aspect+Size)"):
                    self.table.setItem(r, 2, QTableWidgetItem(status))
                break
        self._update_review_button()
        # if filter active, re-apply to hide/show correctly
        if hasattr(self, "mismatch_filter_check") and self.mismatch_filter_check.isChecked():
            # keep filter in sync when new mismatches arrive
            self.apply_mismatch_filter(True)

    def on_progress(self, done: int, total: int, filename: str):
        pct = int(done / total * 100) if total else 0
        self.progress.setValue(pct)
        self.status_label.setText(f"Processed {done} of {total} | Current: {filename}")
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.text() == filename:
                continue

    def on_error(self, path_str: str, msg: str):
        self.status_label.setText(f"Error {Path(path_str).name}: {msg}")

    def _resolve_mismatch(self, action: str):
        if not self.worker:
            # abort mode — just dismiss bar
            self.mismatch_bar.setVisible(False)
            self.btn_apply_once.setVisible(True)
            self.btn_update_std.setVisible(True)
            self.btn_skip.setVisible(True)
            self.btn_mismatch_close.setVisible(False)
            self._batch_aborted = False
            return
        self.mismatch_bar.setVisible(False)
        self.btn_mismatch_close.setVisible(False)
        self.btn_apply_once.setVisible(True)
        self.btn_update_std.setVisible(True)
        self.btn_skip.setVisible(True)
        if action == "apply_once":
            self.worker.resume_apply_once()
        elif action == "update_standard":
            self.config.std_width = self.canvas._page_w
            self.config.std_height = self.canvas._page_h
            self.standard_label.setText(self.config.label())
            self.worker.resume_update_standard()
        elif action == "skip":
            self.worker.resume_skip()

    def on_apply_once(self):
        self._resolve_mismatch("apply_once")

    def on_update_std(self):
        self._resolve_mismatch("update_standard")

    def on_skip(self):
        self._resolve_mismatch("skip")

    def on_mismatch_close(self):
        self.mismatch_bar.setVisible(False)
        self.btn_apply_once.setVisible(True)
        self.btn_update_std.setVisible(True)
        self.btn_skip.setVisible(True)
        self.btn_mismatch_close.setVisible(False)
        self.status_label.setText("Batch aborted — switch to Manual to handle remaining files")
        self._batch_aborted = False

    def on_finished(self):
        was_aborted = self._batch_aborted
        self.start_btn.setEnabled(True)
        self.browse_input_btn.setEnabled(True)
        self.browse_stamp_btn.setEnabled(True)
        self.validate_start()
        self.worker = None
        mismatches = self._mismatch_rows()
        if was_aborted:
            # keep mismatch bar visible so user sees abort reason, allow Manual switch
            self.status_label.setText(f"Batch STOPPED — {self.table.rowCount()} files — {len(mismatches)} mismatch — switch to Manual to review")
            self._update_review_button()
            # do not hide mismatch_bar, keep close button visible
            return
        self.progress.setValue(100)
        self.mismatch_bar.setVisible(False)
        self.btn_mismatch_close.setVisible(False)
        self.btn_apply_once.setVisible(True)
        self.btn_update_std.setVisible(True)
        self.btn_skip.setVisible(True)
        self._batch_aborted = False
        if mismatches and self.config.auto_skip_mismatches:
            self.status_label.setText(f"Batch done — {len(mismatches)} mismatches auto-skipped — click 'Review mismatches → Manual' to edit only mismatches")
            # highlight review button
            self.btn_review_mismatches.setStyleSheet("background: #34c759; color: white; font-weight: bold; border-radius: 6px;")
            # optionally auto-show mismatch bar as info
            self.mismatch_label.setText(f"{len(mismatches)} mismatches auto-skipped — switch to Manual filtered view to edit")
            # don't show abort bar, just keep queue filter ready
        elif mismatches:
            self.status_label.setText(f"Batch done — {self.table.rowCount()} files processed — {len(mismatches)} mismatch — use filter to review")
        else:
            self.status_label.setText(f"Batch done — {self.table.rowCount()} files processed")
            self.btn_review_mismatches.setStyleSheet("background: #FFE9E9; font-weight: bold;")
        self._update_review_button()
        if not mismatches:
            QMessageBox.information(self, "Done", "Batch stamping completed.")
        else:
            # don't block with modal when mismatches need review; show non-blocking info
            if not self.config.auto_skip_mismatches:
                QMessageBox.information(self, "Done", f"Batch completed with {len(mismatches)} mismatches — use 'Show only mismatches' to review in Manual mode.")
            else:
                QMessageBox.information(self, "Done", f"Batch done — {len(mismatches)} mismatches auto-skipped — click 'Review mismatches → Manual' to edit only those files.")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.pause_event.set()
            self.worker.requestInterruption()
            self.worker.wait(2000)
        event.accept()
