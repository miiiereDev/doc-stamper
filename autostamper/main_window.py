import threading
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QSplitter,
    QGroupBox, QRadioButton, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QFrame, QMessageBox, QStackedWidget
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
        self.mode = "manual"
        self.manual_index = 0

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
        main_layout.addWidget(self.mismatch_bar)

        splitter = QSplitter(Qt.Horizontal)

        self.canvas = PDFCanvasWidget(self.config)
        splitter.addWidget(self.canvas)

        right = QWidget()
        right.setMinimumWidth(320)
        right.setMaximumWidth(420)
        r_layout = QVBoxLayout(right)
        r_layout.setContentsMargins(6, 6, 6, 6)

        mode_grp = QGroupBox("Mode")
        m_layout = QVBoxLayout(mode_grp)
        self.radio_manual = QRadioButton("Manual — One by one (Default)")
        self.radio_auto = QRadioButton("Automatic — Batch with Standard")
        self.radio_manual.setChecked(True)
        m_layout.addWidget(self.radio_manual)
        m_layout.addWidget(self.radio_auto)
        r_layout.addWidget(mode_grp)

        grp = QGroupBox("Target Page")
        g_layout = QVBoxLayout(grp)
        self.radio_last = QRadioButton("Last Page (Default)")
        self.radio_first = QRadioButton("First Page")
        self.radio_last.setChecked(True)
        g_layout.addWidget(self.radio_last)
        g_layout.addWidget(self.radio_first)
        r_layout.addWidget(grp)

        self.aspect_check = QCheckBox("Lock aspect ratio")
        self.aspect_check.setToolTip("Prevent stamp from stretching — keep original image proportions")
        r_layout.addWidget(self.aspect_check)

        self.stack = QStackedWidget()
        # manual panel
        manual_page = QWidget()
        mp_layout = QVBoxLayout(manual_page)
        mp_layout.setContentsMargins(0, 0, 0, 0)
        self.manual_info = QLabel("No files")
        self.manual_info.setStyleSheet("color: #333; font-weight: bold;")
        mp_layout.addWidget(self.manual_info)
        nav = QHBoxLayout()
        self.manual_prev = QPushButton("◀ Prev")
        self.manual_next = QPushButton("Next ▶")
        nav.addWidget(self.manual_prev)
        nav.addWidget(self.manual_next)
        mp_layout.addLayout(nav)
        self.manual_stamp_btn = QPushButton("Stamp & Save This File")
        self.manual_stamp_btn.setMinimumHeight(32)
        self.manual_stamp_btn.setStyleSheet("QPushButton { background: #34c759; color: white; font-weight: bold; border-radius: 6px; } QPushButton:disabled { background: #aaa; }")
        mp_layout.addWidget(self.manual_stamp_btn)
        self.manual_skip_btn = QPushButton("Skip This File")
        mp_layout.addWidget(self.manual_skip_btn)
        self.stack.addWidget(manual_page)

        # auto panel
        auto_page = QWidget()
        ap_layout = QVBoxLayout(auto_page)
        ap_layout.setContentsMargins(0, 0, 0, 0)
        self.lock_btn = QPushButton("Lock Current as Standard")
        self.lock_btn.setCheckable(True)
        ap_layout.addWidget(self.lock_btn)
        self.standard_label = QLabel(self.config.label())
        self.standard_label.setStyleSheet("color: #333; font-size: 12px;")
        ap_layout.addWidget(self.standard_label)
        self.start_btn = QPushButton("Start Batch")
        self.start_btn.setEnabled(False)
        self.start_btn.setMinimumHeight(36)
        self.start_btn.setStyleSheet("QPushButton { background: #0a84ff; color: white; font-weight: bold; border-radius: 6px; } QPushButton:disabled { background: #aaa; }")
        ap_layout.addWidget(self.start_btn)
        self.stack.addWidget(auto_page)

        r_layout.addWidget(self.stack)

        r_layout.addWidget(QLabel("File Queue:"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Filename", "Status", "Dimensions"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        r_layout.addWidget(self.table, 1)

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
        if total == 0:
            self.manual_info.setText("No files")
            self.manual_prev.setEnabled(False)
            self.manual_next.setEnabled(False)
            self.manual_stamp_btn.setEnabled(False)
            self.manual_skip_btn.setEnabled(False)
            return
        self.manual_index = max(0, min(self.manual_index, total - 1))
        cur = self.pdf_paths[self.manual_index]
        status = self.table.item(self.manual_index, 1).text() if self.table.item(self.manual_index, 1) else "Pending"
        self.manual_info.setText(f"File {self.manual_index + 1} of {total}: {cur.name} ({status})")
        self.manual_prev.setEnabled(self.manual_index > 0)
        self.manual_next.setEnabled(self.manual_index < total - 1)
        has_stamp = bool(self.stamp_edit.text() and Path(self.stamp_edit.text()).exists())
        self.manual_stamp_btn.setEnabled(has_stamp and status not in ("Done",))
        self.manual_skip_btn.setEnabled(status not in ("Done", "Skipped"))
        self.progress.setValue(int((self.manual_index / max(1, total)) * 100))

    def manual_prev_file(self):
        if self.manual_index > 0:
            self.manual_index -= 1
            self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
            self.table.selectRow(self.manual_index)
            self.update_manual_ui()

    def manual_next_file(self):
        if self.manual_index < len(self.pdf_paths) - 1:
            self.manual_index += 1
            self.canvas.load_pdf(self.pdf_paths[self.manual_index], self.config.target_page)
            self.table.selectRow(self.manual_index)
            self.update_manual_ui()

    def manual_skip_current(self):
        if not self.pdf_paths:
            return
        self.table.setItem(self.manual_index, 1, QTableWidgetItem("Skipped"))
        self.update_manual_ui()
        if self.manual_index < len(self.pdf_paths) - 1:
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
        self.update_manual_ui()
        if self.manual_index < len(self.pdf_paths) - 1:
            self.manual_next_file()
        else:
            self.progress.setValue(100)
            self.status_label.setText(f"Manual done — {len(self.pdf_paths)} files")

    def _connect(self):
        self.browse_input_btn.clicked.connect(self.pick_input)
        self.browse_stamp_btn.clicked.connect(self.pick_stamp)
        self.radio_last.toggled.connect(self.on_target_changed)
        self.radio_manual.toggled.connect(self.on_mode_changed)
        self.lock_btn.clicked.connect(self.on_lock)
        self.aspect_check.toggled.connect(self.on_aspect_toggled)
        self.canvas.config_changed.connect(self.on_canvas_config)
        self.start_btn.clicked.connect(self.start_batch)
        self.manual_prev.clicked.connect(self.manual_prev_file)
        self.manual_next.clicked.connect(self.manual_next_file)
        self.manual_stamp_btn.clicked.connect(self.manual_stamp_current)
        self.manual_skip_btn.clicked.connect(self.manual_skip_current)
        self.btn_apply_once.clicked.connect(self.on_apply_once)
        self.btn_update_std.clicked.connect(self.on_update_std)
        self.btn_skip.clicked.connect(self.on_skip)
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
        for pdf in self.pdf_paths:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(pdf.name))
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

    def on_canvas_config(self, cfg):
        self.config = cfg
        self.aspect_check.setChecked(cfg.keep_aspect)
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
        for r in range(self.table.rowCount()):
            self.table.setItem(r, 1, QTableWidgetItem("Pending"))

        self.start_btn.setEnabled(False)
        self.browse_input_btn.setEnabled(False)
        self.browse_stamp_btn.setEnabled(False)

        self.pause_event = threading.Event()
        self.worker = StamperWorker(self.pdf_paths, stamp_path, self.config, self.pause_event, input_dir)
        self.worker.mismatch_detected.connect(self.on_mismatch)
        self.worker.progress.connect(self.on_progress)
        self.worker.file_status.connect(self.on_file_status)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_mismatch(self, path_str: str, page_idx: int, w: float, h: float):
        self._mismatch_path = Path(path_str)
        self.mismatch_label.setText(f"Dimension Mismatch: {self._mismatch_path.name} ({w:.1f} x {h:.1f} pt)")
        self.mismatch_bar.setVisible(True)
        self.canvas.load_pdf(self._mismatch_path, self.config.target_page)
        self.status_label.setText(f"Paused — mismatch {self._mismatch_path.name} ({w:.1f} x {h:.1f} pt)")

    def on_file_status(self, path_str: str, status: str):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.data(Qt.UserRole) == path_str:
                self.table.setItem(r, 1, QTableWidgetItem(status))
                if status == "Mismatch":
                    self.table.setItem(r, 2, QTableWidgetItem(status))
                break

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
            return
        self.mismatch_bar.setVisible(False)
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

    def on_finished(self):
        self.status_label.setText(f"Batch done — {self.table.rowCount()} files processed")
        self.progress.setValue(100)
        self.mismatch_bar.setVisible(False)
        self.start_btn.setEnabled(True)
        self.browse_input_btn.setEnabled(True)
        self.browse_stamp_btn.setEnabled(True)
        self.validate_start()
        self.worker = None
        QMessageBox.information(self, "Done", "Batch stamping completed.")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.pause_event.set()
            self.worker.requestInterruption()
            self.worker.wait(2000)
        event.accept()
