import threading
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QSplitter,
    QGroupBox, QRadioButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QFrame, QMessageBox
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

        self._build_ui()
        self._connect()

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

        grp = QGroupBox("Target Page")
        g_layout = QVBoxLayout(grp)
        self.radio_last = QRadioButton("Last Page (Default)")
        self.radio_first = QRadioButton("First Page")
        self.radio_last.setChecked(True)
        g_layout.addWidget(self.radio_last)
        g_layout.addWidget(self.radio_first)
        r_layout.addWidget(grp)

        self.lock_btn = QPushButton("Lock Current as Standard")
        self.lock_btn.setCheckable(True)
        r_layout.addWidget(self.lock_btn)

        self.standard_label = QLabel(self.config.label())
        self.standard_label.setStyleSheet("color: #333; font-size: 12px;")
        r_layout.addWidget(self.standard_label)

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

        self.start_btn = QPushButton("Start Batch")
        self.start_btn.setEnabled(False)
        self.start_btn.setMinimumHeight(36)
        self.start_btn.setStyleSheet("QPushButton { background: #0a84ff; color: white; font-weight: bold; border-radius: 6px; } QPushButton:disabled { background: #aaa; }")
        r_layout.addWidget(self.start_btn)

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

    def _connect(self):
        self.browse_input_btn.clicked.connect(self.pick_input)
        self.browse_stamp_btn.clicked.connect(self.pick_stamp)
        self.radio_last.toggled.connect(self.on_target_changed)
        self.lock_btn.clicked.connect(self.on_lock)
        self.canvas.config_changed.connect(self.on_canvas_config)
        self.start_btn.clicked.connect(self.start_batch)
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

        self.validate_start()

    def on_target_changed(self):
        self.config.target_page = "first" if self.radio_first.isChecked() else "last"
        if self.pdf_paths:
            self.canvas.load_pdf(self.pdf_paths[0], self.config.target_page)
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

    def on_canvas_config(self, cfg):
        self.config = cfg
        if self.config.is_locked:
            self.standard_label.setText(self.config.label())

    def validate_start(self):
        has_input = bool(self.input_edit.text() and self.pdf_paths)
        has_stamp = bool(self.stamp_edit.text() and Path(self.stamp_edit.text()).exists())
        self.start_btn.setEnabled(has_input and has_stamp and self.worker is None)

    def on_table_click(self, row, _col):
        item = self.table.item(row, 0)
        if not item:
            return
        path = Path(str(item.data(Qt.UserRole)))
        if path.exists():
            self.canvas.load_pdf(path, self.config.target_page)

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
