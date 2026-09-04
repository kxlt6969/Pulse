import platform as _platform
from collections import deque
from datetime import datetime

import psutil
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__, theme
from .charts import LiveChart
from .collectors import MonitorWorker
from .fmt import human_bytes, human_duration, human_speed
from .processes import ProcessTable
from .widgets import CoreBars, GaugeWidget, LogoWidget, NetStat


class MainWindow(QMainWindow):
    def __init__(self, interval=1.0, top=25):
        super().__init__()
        self._interval = interval
        self._top = top
        self._cpu_hist = deque(maxlen=60)
        self._net_down_hist = deque(maxlen=60)
        self._net_up_hist = deque(maxlen=60)
        self._disks_by_mount = {}

        self._build_ui()

        self._worker = MonitorWorker(interval=interval, process_limit=top)
        self._worker.snapshot_ready.connect(self._on_snapshot)
        self._worker.start()

    def _build_ui(self):
        self.setWindowTitle("Pulse — System Monitor")
        self.setMinimumSize(1180, 820)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 18, 20, 10)
        root.setSpacing(14)

        root.addLayout(self._build_header())
        root.addLayout(self._build_gauge_row())
        root.addLayout(self._build_chart_row())
        root.addWidget(self._build_process_card(), 1)
        self._build_status_bar()

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(14)

        logo = LogoWidget()
        logo.setFixedSize(46, 46)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("Pulse")
        title.setObjectName("appTitle")
        subtitle = QLabel("Real-time system monitor")
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)

        self.host_chip = self._chip(_platform.node() or "localhost")
        self.os_chip = self._chip(f"{_platform.system()} {_platform.release()}")
        self.uptime_chip = self._chip("up —")
        self.battery_chip = self._chip("")
        self.battery_chip.hide()

        header.addWidget(logo)
        header.addLayout(titles)
        header.addStretch(1)
        header.addWidget(self.host_chip)
        header.addWidget(self.os_chip)
        header.addWidget(self.uptime_chip)
        header.addWidget(self.battery_chip)
        return header

    def _build_gauge_row(self):
        row = QHBoxLayout()
        row.setSpacing(14)

        # CPU
        self.cpu_gauge = GaugeWidget(theme.CPU)
        self.core_bars = CoreBars(theme.CPU)
        self.cpu_sub = self._sub("—")
        cpu_card, layout = self._make_card("CPU")
        layout.addWidget(self.cpu_gauge)
        layout.addWidget(self.core_bars)
        layout.addWidget(self.cpu_sub)

        # Memory
        self.ram_gauge = GaugeWidget(theme.RAM)
        self.ram_sub = self._sub("—")
        ram_card, layout = self._make_card("MEMORY")
        layout.addWidget(self.ram_gauge)
        layout.addStretch(1)
        layout.addWidget(self.ram_sub)

        # Disk
        self.disk_gauge = GaugeWidget(theme.DISK)
        self.disk_combo = QComboBox()
        self.disk_combo.currentIndexChanged.connect(lambda _=None: self._update_disk_gauge())
        self.disk_sub = self._sub("—")
        disk_card, layout = self._make_card("DISK")
        layout.addWidget(self.disk_combo)
        layout.addWidget(self.disk_gauge)
        layout.addStretch(1)
        layout.addWidget(self.disk_sub)

        # Network
        self.down_stat = NetStat("↓", theme.NET_DOWN, "DOWNLOAD")
        self.up_stat = NetStat("↑", theme.NET_UP, "UPLOAD")
        self.net_sub = self._sub("—")
        net_card, layout = self._make_card("NETWORK")
        layout.addWidget(self.down_stat)
        layout.addWidget(self.up_stat)
        layout.addStretch(1)
        layout.addWidget(self.net_sub)

        for card in (cpu_card, ram_card, disk_card, net_card):
            row.addWidget(card, 1)
        return row

    def _build_chart_row(self):
        row = QHBoxLayout()
        row.setSpacing(14)

        self.cpu_now_chip = self._value_chip(theme.CPU, "0%")
        self.cpu_chart = LiveChart(max_points=60)
        self.cpu_chart.add_series("cpu", theme.CPU)
        self.cpu_chart.set_ylim(0, 100)
        self.cpu_chart.setMinimumHeight(185)
        cpu_card, layout = self._make_card("CPU HISTORY", "last 60 seconds", [self.cpu_now_chip])
        layout.addWidget(self.cpu_chart)

        self.net_down_chip = self._value_chip(theme.NET_DOWN, "↓ 0 B/s")
        self.net_up_chip = self._value_chip(theme.NET_UP, "↑ 0 B/s")
        self.net_chart = LiveChart(max_points=60, left_axis="speed")
        self.net_chart.add_series("down", theme.NET_DOWN)
        self.net_chart.add_series("up", theme.NET_UP)
        self.net_chart.setMinimumHeight(185)
        net_card, layout = self._make_card("NETWORK ACTIVITY", "last 60 seconds", [self.net_down_chip, self.net_up_chip])
        layout.addWidget(self.net_chart)

        row.addWidget(cpu_card, 3)
        row.addWidget(net_card, 2)
        return row

    def _build_process_card(self):
        self.end_btn = QPushButton("End task")
        self.end_btn.setObjectName("endTask")
        self.end_btn.setEnabled(False)
        self.end_btn.clicked.connect(self._end_task)

        card, layout = self._make_card("PROCESSES", f"top {self._top} by CPU", [self.end_btn])
        self.table = ProcessTable()
        self.table.itemSelectionChanged.connect(
            lambda: self.end_btn.setEnabled(self.table.currentRow() >= 0)
        )
        layout.addWidget(self.table)
        return card

    def _build_status_bar(self):
        bar = self.statusBar()
        self.status_label = QLabel("Starting…")
        bar.addWidget(self.status_label)
        bar.addPermanentWidget(QLabel(f"Python {_platform.python_version()} · Pulse v{__version__}"))

    # ----------------------------------------------------------- helpers

    @staticmethod
    def _chip(text):
        label = QLabel(text)
        label.setObjectName("chip")
        return label

    @staticmethod
    def _sub(text):
        label = QLabel(text)
        label.setObjectName("subValue")
        return label

    @staticmethod
    def _value_chip(color, text):
        chip = QLabel(text)
        chip.setObjectName("chip")
        chip.setStyleSheet(f"color: {color}; font-weight: 700;")
        return chip

    @staticmethod
    def _make_card(title, subtitle=None, header_widgets=()):
        card = QFrame()
        card.setObjectName("card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        head.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("cardSub")
            head.addWidget(sub)
        head.addStretch(1)
        for widget in header_widgets:
            head.addWidget(widget)
        outer.addLayout(head)
        return card, outer

    # ---------------------------------------------------------- live data

    def _on_snapshot(self, snapshot):
        # CPU
        self.cpu_gauge.set_value(snapshot.cpu_percent)
        self.core_bars.set_values(snapshot.cpu_per_core)
        parts = []
        if snapshot.cpu_freq:
            parts.append(f"{snapshot.cpu_freq / 1000.0:.2f} GHz")
        parts.append(f"{snapshot.cores_logical} threads")
        if snapshot.cores_physical:
            parts.append(f"{snapshot.cores_physical} cores")
        self.cpu_sub.setText(" · ".join(parts))

        # Memory
        self.ram_gauge.set_value(snapshot.mem_percent)
        ram_text = f"{human_bytes(snapshot.mem_used)} / {human_bytes(snapshot.mem_total)}"
        if snapshot.swap_total:
            ram_text += f" · swap {human_bytes(snapshot.swap_used)}"
        self.ram_sub.setText(ram_text)

        # Disk
        self._disks_by_mount = {d.mount: d for d in snapshot.disks}
        self._refresh_disk_combo()
        self._update_disk_gauge()

        # Network stats
        self.down_stat.set_value(human_speed(snapshot.net_down))
        self.up_stat.set_value(human_speed(snapshot.net_up))
        self.net_sub.setText(
            f"since boot  ↓ {human_bytes(snapshot.net_total_down)}  ·  ↑ {human_bytes(snapshot.net_total_up)}"
        )

        # Charts
        self._cpu_hist.append(snapshot.cpu_percent)
        self.cpu_chart.push("cpu", list(self._cpu_hist))
        self.cpu_now_chip.setText(f"{snapshot.cpu_percent:.0f}%")

        self._net_down_hist.append(snapshot.net_down)
        self._net_up_hist.append(snapshot.net_up)
        self.net_chart.push("down", list(self._net_down_hist))
        self.net_chart.push("up", list(self._net_up_hist))
        peak = max(self._net_down_hist) if self._net_down_hist else 0.0
        if self._net_up_hist:
            peak = max(peak, max(self._net_up_hist))
        self.net_chart.set_ylim(0.0, max(peak * 1.25, 8 * 1024))
        self.net_down_chip.setText(f"↓ {human_speed(snapshot.net_down)}")
        self.net_up_chip.setText(f"↑ {human_speed(snapshot.net_up)}")

        # Processes
        self.table.update_rows(snapshot.processes)

        # Header chips + status bar
        self.uptime_chip.setText(f"up {human_duration(snapshot.uptime)}")
        if snapshot.battery:
            pct, plugged, secs_left = snapshot.battery
            text = f"⚡ {pct:.0f}%"
            if not plugged and secs_left:
                text += f" · {human_duration(secs_left)} left"
            self.battery_chip.setText(text)
            self.battery_chip.show()

        stamp = datetime.now().strftime("%H:%M:%S")
        self.status_label.setText(
            f"Live · updated {stamp} · refresh {self._interval:g}s · tracking {len(snapshot.processes)} processes"
        )

    def _refresh_disk_combo(self):
        mounts = list(self._disks_by_mount.keys())[:6]
        current = [self.disk_combo.itemText(i) for i in range(self.disk_combo.count())]
        if current != mounts:
            selected = self.disk_combo.currentText()
            self.disk_combo.blockSignals(True)  # don't double-update while rebuilding
            self.disk_combo.clear()
            self.disk_combo.addItems(mounts)
            if selected in mounts:
                self.disk_combo.setCurrentText(selected)
            self.disk_combo.blockSignals(False)
            self.disk_combo.setVisible(bool(mounts))

    def _update_disk_gauge(self):
        info = self._disks_by_mount.get(self.disk_combo.currentText())
        if info is None and self._disks_by_mount:
            info = next(iter(self._disks_by_mount.values()))
        if info is not None:
            self.disk_gauge.set_value(info.percent)
            self.disk_sub.setText(f"{human_bytes(info.used)} / {human_bytes(info.total)} · {info.fstype}")

    def _end_task(self):
        pid = self.table.selected_pid()
        if pid is None:
            return
        row = self.table.currentRow()
        name_item = self.table.item(row, 1)
        name = name_item.text() if name_item else str(pid)
        confirm = QMessageBox.question(
            self,
            "End task",
            f"Terminate “{name}” (PID {pid})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            psutil.Process(pid).terminate()
            self.statusBar().showMessage(f"Sent terminate signal to PID {pid}", 4000)
        except psutil.NoSuchProcess:
            self.statusBar().showMessage(f"PID {pid} already exited", 4000)
        except Exception as exc:
            QMessageBox.warning(self, "End task failed", f"Could not terminate PID {pid}:\n{exc}")

    def closeEvent(self, event):
        self._worker.stop()
        super().closeEvent(event)
