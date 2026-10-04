import json
import platform as _platform
import sys
import time
from collections import deque
from datetime import datetime

import psutil
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QKeySequence, QShortcut, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import __version__, theme
from .actions import ProcessActions, process_actions
from .charts import LiveChart
from .collectors import GpuWorker, MonitorWorker

from .fmt import human_bytes, human_duration, human_speed
from .processes import ProcessTable
from .widgets import (
    CoreBars,
    GaugeWidget,
    LogoWidget,
    MiniOverlay,
    NetStat,
    TemperatureCard,
)


def apply_titlebar(window, dark=True):
    # windows 10/11 only, harmless anywhere else
    if sys.platform != "win32":
        return
    import ctypes

    try:
        hwnd = int(window.winId())
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE, new value first
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), 4) == 0:
                break
    except Exception:
        pass


def snapshot_temps_available():
    # thin wrapper so app.py doesn't poke at a private collector
    try:
        return bool(psutil.sensors_temperatures())
    except Exception:
        return False


class MainWindow(QMainWindow):
    def __init__(self, interval=1.0, top=25, lite=False, gpu=True, log_file=None):
        super().__init__()
        self._interval = interval
        self._top = top
        self._lite = bool(lite)
        self._net_scale = 8.0 * 1024 * 1024
        self._last_snapshot = None
        self._paused = False
        self._autoscale = False  # restore_settings() may flip this
        self._watched = set()  # survives theme rebuilds, the table re-reads it
        self._process_actions = ProcessActions(self)
        self._process_actions.connect_status(self)
        self._history = {}  # chart buffers, created lazily
        self._alerts_enabled = True
        self._alert_state = {}
        self._alert_timer = QTimer(self)
        self._alert_timer.setInterval(10_000)
        self._alert_timer.timeout.connect(self._check_alerts)

        # settings writes are debounced; the registry hates being poked
        # 60x while someone drags a slider
        self._save_interval = QTimer(self)
        self._save_interval.setSingleShot(True)
        self._save_interval.setInterval(1500)
        self._save_interval.timeout.connect(self._write_interval)

        self._theme_save = QTimer(self)
        self._theme_save.setSingleShot(True)
        self._theme_save.setInterval(1500)
        self._theme_save.timeout.connect(self._save_theme)

        # snapshot frames are coalesced: paint the first one immediately,
        # then hold the rest in _pending until this timer fires, so a slow
        # ui thread drops frames instead of stacking repaints
        self._pending = None
        self._coalesce = QTimer(self)
        self._coalesce.setSingleShot(True)
        self._coalesce.setInterval(120)
        self._coalesce.timeout.connect(self._paint_pending)
        self._disks_by_mount = {}
        self._last_disk = None
        self._gpu_name_full = ""
        self._quitting = False
        self._tray_notified = False
        self._tray_tip = ""
        self._tray_hist = deque(maxlen=8)  # for the tiny bars in the tray icon
        self._tray_paints = 0  # tray icon updates are capped, see _update_tray_icon
        self.tray = None
        self.overlay_action = None
        self.light_theme_action = None

        # gpu availability decides whether the GPU card exists, so the gpu
        # worker needs to exist before the ui is built
        self._worker = MonitorWorker(interval=interval, process_limit=top)
        self._gpu_worker = GpuWorker() if gpu else GpuWorker(skip=True)
        self._alert_timer.start()
        self._gpu_info = None
        self._build_ui()
        self._build_status_bar()

        if not self._lite:
            self.overlay = MiniOverlay()
            self.overlay.on_close = self._overlay_closed
            self.overlay.on_open = self._show_window
        else:
            self.overlay = None

        self._build_tray()

        self._worker.snapshot_ready.connect(self._on_snapshot)
        self._worker.start()
        self._install_shortcuts()
        self.restore_settings()
        self._log_file = None
        if log_file:
            try:
                # line-buffered append; one json line per tick
                self._log_file = open(log_file, "a", buffering=1, encoding="utf-8")
            except OSError as exc:
                print(f"[pulse] can't open log file: {exc!r}")
        if self._gpu_worker.available():
            self._gpu_worker.gpu_ready.connect(self._on_gpu)
            self._gpu_worker.start()

    def _build_ui(self):
        # called again on theme switch; setCentralWidget deletes the old tree
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 18, 20, 10)
        root.setSpacing(14)

        root.addLayout(self._build_header())
        root.addLayout(self._build_gauge_row())
        for gauge in self._gauges():  # needle ease must fit the refresh rate
            gauge.set_rate(self._interval)
        if self._lite:
            # one-line shortcut for the low-memory crowd; charts are the
            # only part of the ui that keeps growing things
            root.addWidget(self._build_process_card(), 1)
            return
        root.addLayout(self._build_chart_row())
        root.addWidget(self._build_process_card(), 1)

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

        self.theme_btn = QPushButton("light" if theme.is_dark() else "dark")
        self.theme_btn.setObjectName("ghost")
        self.theme_btn.setToolTip("Switch theme")
        self.theme_btn.clicked.connect(self._toggle_theme)

        self.alerts_btn = QPushButton("alerts")
        self.alerts_btn.setObjectName("ghost")
        self.alerts_btn.setToolTip("CPU / RAM alerts")
        self.alerts_btn.clicked.connect(self._show_alerts_dialog)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("ghost")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self._show_settings)

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
        header.addWidget(self.alerts_btn)
        header.addWidget(self.settings_btn)
        header.addWidget(self.theme_btn)
        return header

    def _build_gauge_row(self):
        row = QHBoxLayout()
        row.setSpacing(14)

        # CPU
        self.cpu_gauge = GaugeWidget("CPU")
        self.core_bars = CoreBars("CPU")
        self.cpu_sub = self._sub("—")
        cpu_card, layout = self._make_card("CPU")
        layout.addWidget(self.cpu_gauge)
        layout.addWidget(self.core_bars)
        layout.addWidget(self.cpu_sub)
        row.addWidget(cpu_card, 1)

        # GPU (only when a usable source was found)
        self.gpu_gauge = None
        if self._gpu_worker.available():
            self.gpu_gauge = GaugeWidget("GPU")
            self.gpu_name = self._sub(self._gpu_worker.name or "GPU")
            self.gpu_sub = self._sub("reading…")
            gpu_card, layout = self._make_card("GPU")
            layout.addWidget(self.gpu_gauge)
            layout.addStretch(1)
            layout.addWidget(self.gpu_name)
            layout.addWidget(self.gpu_sub)
            row.addWidget(gpu_card, 1)

        # Memory
        self.ram_gauge = GaugeWidget("RAM")
        self.ram_sub = self._sub("—")
        ram_card, layout = self._make_card("MEMORY")
        layout.addWidget(self.ram_gauge)
        layout.addStretch(1)
        layout.addWidget(self.ram_sub)
        row.addWidget(ram_card, 1)

        # Disk
        self.disk_gauge = GaugeWidget("DISK")
        self.disk_combo = QComboBox()
        self.disk_combo.currentIndexChanged.connect(lambda _=None: self._update_disk_gauge())
        self.disk_sub = self._sub("—")
        disk_card, layout = self._make_card("DISK")
        layout.addWidget(self.disk_combo)
        layout.addWidget(self.disk_gauge)
        layout.addStretch(1)
        layout.addWidget(self.disk_sub)
        row.addWidget(disk_card, 1)

        # Network
        self.down_stat = NetStat("↓", theme.NET_DOWN, "DOWNLOAD")
        self.up_stat = NetStat("↑", theme.NET_UP, "UPLOAD")
        self.net_sub = self._sub("—")
        net_card, layout = self._make_card("NETWORK")
        layout.addWidget(self.down_stat)
        layout.addWidget(self.up_stat)
        layout.addStretch(1)
        layout.addWidget(self.net_sub)
        row.addWidget(net_card, 1)

        # temps are best-effort; the card vanishes if the kernel says nothing
        self.temp_card = None
        if snapshot_temps_available():
            self.temp_card = TemperatureCard()
            temp_card, layout = self._make_card("TEMP")
            layout.addWidget(self.temp_card)
            layout.addStretch(1)
            row.addWidget(temp_card, 1)

        return row

    def _build_chart_row(self):
        row = QHBoxLayout()
        row.setSpacing(14)

        self.cpu_now_chip = self._value_chip(theme.CPU, "0%")
        self.cpu_chart = LiveChart(max_points=60)
        self.cpu_chart.add_series("cpu", "CPU")
        self.cpu_chart.set_ylim(0, 100)
        self.cpu_chart.setMinimumHeight(185)
        cpu_card, layout = self._make_card("CPU HISTORY", "last 60 seconds", [self.cpu_now_chip])
        layout.addWidget(self.cpu_chart)

        self.net_down_chip = self._value_chip(theme.NET_DOWN, "↓ 0 B/s")
        self.net_up_chip = self._value_chip(theme.NET_UP, "↑ 0 B/s")
        self.net_chart = LiveChart(max_points=60, left_axis="speed")
        self.net_chart.add_series("down", "NET_DOWN")
        self.net_chart.add_series("up", "NET_UP")
        self.net_chart.setMinimumHeight(185)
        net_card, layout = self._make_card("NETWORK ACTIVITY", "last 60 seconds", [self.net_down_chip, self.net_up_chip])
        layout.addWidget(self.net_chart)

        row.addWidget(cpu_card, 3)
        row.addWidget(net_card, 2)

        # disk activity, same rolling treatment as network. no subtitle in
        # the header — title + two chips already overflow this narrow card
        self.disk_read_chip = self._value_chip(theme.DISK, "R 0 B/s")
        self.disk_write_chip = self._value_chip(theme.DISK, "W 0 B/s")
        self.disk_chart = LiveChart(max_points=60, left_axis="speed")
        self.disk_chart.add_series("read", "DISK")
        self.disk_chart.add_series("write", "NET_UP")
        self.disk_chart.setMinimumHeight(150)
        disk_card, layout = self._make_card("DISK ACTIVITY", None, [self.disk_read_chip, self.disk_write_chip])
        layout.addWidget(self.disk_chart)
        row.addWidget(disk_card, 1)
        return row

    def _build_process_card(self):
        self.end_btn = QPushButton("End task")
        self.end_btn.setObjectName("endTask")
        self.end_btn.setEnabled(False)
        self.end_btn.clicked.connect(self._end_task)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("filter…")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.setFixedWidth(170)

        card, layout = self._make_card(
            "PROCESSES", f"top {self._top} by CPU", [self.filter_input, self.end_btn]
        )

        self.table = ProcessTable()
        self.filter_input.textChanged.connect(self.table.set_filter)
        self.table.itemSelectionChanged.connect(
            lambda: self.end_btn.setEnabled(self.table.currentRow() >= 0)
        )
        self.table.context_menu.connect(self._process_menu)
        self.table.open_details.connect(self._show_detail)
        self.table.watch_changed.connect(self._on_watch_changed)
        for pid in self._watched:  # re-apply after a theme rebuild
            self.table.watch_pid(pid)
        layout.addWidget(self.table)
        return card

    def _on_watch_changed(self, pids):
        self._watched = set(pids)
        # pinned processes survive restarts; cheap, and people notice
        QSettings("kxlt6969", "Pulse").setValue("watchlist", sorted(self._watched))

    def _build_status_bar(self):
        bar = self.statusBar()
        self.status_label = QLabel("Starting…")
        bar.addWidget(self.status_label)

        self.interval_slider = QSlider(Qt.Orientation.Horizontal)
        self.interval_slider.setRange(5, 100)  # 0.5s .. 10s
        self.interval_slider.setFixedWidth(110)
        self.interval_slider.setToolTip("Refresh interval (0.5s – 10s)")
        self.interval_slider.setValue(self._interval_to_slider(self._interval))
        self.interval_slider.valueChanged.connect(self._interval_changed)
        self.interval_label = QLabel(f"{self._interval:g}s")
        bar.addPermanentWidget(self.interval_label)
        bar.addPermanentWidget(self.interval_slider)
        bar.addPermanentWidget(QLabel(f"Python {_platform.python_version()} · Pulse v{__version__}"))

    @staticmethod
    def _interval_to_slider(interval):
        return max(5, min(100, int(round(interval * 10))))

    def _interval_changed(self, value):
        self._interval = value / 10.0
        self._worker.interval = self._interval
        for gauge in self._gauges():
            gauge.set_rate(self._interval)
        self.interval_label.setText(f"{self._interval:g}s")
        self._save_interval.start()

    def _gauges(self):
        for gauge in (
            self.cpu_gauge,
            self.gpu_gauge,
            self.ram_gauge,
            self.disk_gauge,
        ):
            if gauge is not None:
                yield gauge

    def _write_interval(self):
        QSettings("kxlt6969", "Pulse").setValue("run/interval", self._interval)

    # --- tray ---

    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        logo = LogoWidget()
        logo.resize(64, 64)
        self.tray = QSystemTrayIcon(QIcon(logo.grab()), self)
        self.tray.setToolTip("Pulse")

        menu = QMenu()

        open_action = menu.addAction("Open dashboard")
        open_action.triggered.connect(self._show_window)

        if self.overlay is not None:
            self.overlay_action = menu.addAction("Mini overlay")
            self.overlay_action.setCheckable(True)
            self.overlay_action.toggled.connect(self._set_overlay_visible)

        self.light_theme_action = menu.addAction("Light theme")
        self.light_theme_action.setCheckable(True)
        self.light_theme_action.setChecked(not theme.is_dark())
        self.light_theme_action.toggled.connect(self._on_tray_theme_toggle)

        self.pause_action = menu.addAction("Pause updates")
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self._toggle_pause)
        self.pause_action.setEnabled(not self._lite)

        alerts_action = menu.addAction("CPU/RAM alerts")
        alerts_action.setCheckable(True)
        alerts_action.setChecked(self._alerts_enabled)
        alerts_action.toggled.connect(self._set_alerts_enabled)

        settings_action = menu.addAction("Settings…")
        settings_action.triggered.connect(self._show_settings)

        about_action = menu.addAction("About Pulse")
        about_action.triggered.connect(self._show_about)

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _show_window(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        if self._last_snapshot is not None:
            # hidden windows skipped their paints; catch up on what changed
            self._paint_snapshot(self._last_snapshot)

    def _tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self._show_window()

    def _set_overlay_visible(self, visible):
        if self.overlay is None:
            return
        self.overlay.setVisible(visible)
        if visible:
            self.overlay.raise_()

    def _overlay_closed(self):
        if self.overlay_action is not None:
            self.overlay_action.setChecked(False)

    def _quit(self):
        self._quitting = True
        if self.overlay is not None:
            self.overlay.hide()
        self._worker.stop()
        self._gpu_worker.stop()
        QApplication.instance().quit()

    def force_exit(self):
        # for --screenshot: quit for real instead of hiding to the tray
        self._quitting = True
        if self.overlay is not None:
            self.overlay.hide()
        self._worker.stop()
        self._gpu_worker.stop()
        self.close()

    # --- theme ---

    def _toggle_theme(self):
        if theme.is_dark():
            theme.use_light()
        else:
            theme.use_dark()
        self._theme_save.start()  # write settings once the flipping settles
        self._apply_theme()

    def _save_theme(self):
        QSettings("kxlt6969", "Pulse").setValue("run/theme", "dark" if theme.is_dark() else "light")

    def _on_tray_theme_toggle(self, checked):
        if bool(checked) == theme.is_dark():  # state already matches, nothing to do
            return
        self._toggle_theme()

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(theme.stylesheet())
        apply_titlebar(self, dark=theme.is_dark())
        if self.light_theme_action is not None:
            self.light_theme_action.blockSignals(True)
            self.light_theme_action.setChecked(not theme.is_dark())
            self.light_theme_action.blockSignals(False)
        self._build_ui()  # rebuild with the new palette

    # helpers

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

    # live data

    def _on_snapshot(self, snapshot):
        # receiver half: runs for every tick no matter how busy the ui is.
        # cheap on purpose — store, log, and either paint now or hand the
        # frame to the coalescer.
        if self._paused:
            return  # freeze: keep the last frame on screen
        self._last_snapshot = snapshot
        self._write_log(snapshot)
        if self._coalesce.isActive():
            self._pending = snapshot  # newer frame wins when the timer fires
        else:
            self._paint_snapshot(snapshot)
            self._coalesce.start()

    def _paint_pending(self):
        if self._pending is not None:
            snapshot = self._pending
            self._pending = None
            self._paint_snapshot(snapshot)

    def _paint_snapshot(self, snapshot):
        if not self.isVisible():
            # running hidden in the tray: just remember the frame. painting
            # for nobody is the cheapest way to save the battery, and the
            # window repaints from _last_snapshot the moment it's shown
            return
        self.cpu_gauge.set_value(snapshot.cpu_percent)
        self.core_bars.set_values(snapshot.cpu_per_core)
        parts = []
        if snapshot.cpu_freq:
            parts.append(f"{snapshot.cpu_freq / 1000.0:.2f} GHz")
        parts.append(f"{snapshot.cores_logical} threads")
        if snapshot.cores_physical:
            parts.append(f"{snapshot.cores_physical} cores")
        self.cpu_sub.setText(" · ".join(parts))

        self.ram_gauge.set_value(snapshot.mem_percent)
        ram_text = f"{human_bytes(snapshot.mem_used)} / {human_bytes(snapshot.mem_total)}"
        if snapshot.mem_cached:
            ram_text += f" · {human_bytes(snapshot.mem_cached)} cached"
        if snapshot.swap_total:
            ram_text += f" · swap {human_bytes(snapshot.swap_used)}"
        self.ram_sub.setText(ram_text)

        self._disks_by_mount = {d.mount: d for d in snapshot.disks}
        self._refresh_disk_combo()
        self._update_disk_gauge()

        self.down_stat.set_value(human_speed(snapshot.net_down))
        self.up_stat.set_value(human_speed(snapshot.net_up))
        self.net_sub.setText(
            f"since boot  ↓ {human_bytes(snapshot.net_total_down)}  ·  ↑ {human_bytes(snapshot.net_total_up)}"
        )

        if not self._lite:
            self._feed_chart("cpu", snapshot.cpu_percent)
            self._feed_chart("net_down", snapshot.net_down)
            self._feed_chart("net_up", snapshot.net_up)
            self._feed_chart("disk_read", snapshot.disk_read)
            self._feed_chart("disk_write", snapshot.disk_write)
            self.cpu_now_chip.setText(f"{snapshot.cpu_percent:.0f}%")
            self.net_down_chip.setText(f"↓ {human_speed(snapshot.net_down)}")
            self.net_up_chip.setText(f"↑ {human_speed(snapshot.net_up)}")
            if not self._autoscale:
                self.net_chart.set_ylim(0.0, self._net_scale)
                self.disk_chart.set_ylim(0.0, self._net_scale)
            else:
                peak = max(
                    self._history["net_down"] + self._history["net_up"],
                    default=0.0,
                )
                self.net_chart.set_ylim(0.0, max(peak * 1.25, 8 * 1024))
                dpeak = max(self._history["disk_read"] + self._history["disk_write"], default=0.0)
                self.disk_chart.set_ylim(0.0, max(dpeak * 1.25, 8 * 1024))
        # lite mode still gets the table, tray, everything but the charts

        self.table.update_rows(snapshot.processes)

        self.uptime_chip.setText(f"up {human_duration(snapshot.uptime)}")
        if snapshot.battery:
            pct, plugged, secs_left = snapshot.battery
            text = f"⚡ {pct:.0f}%"
            if not plugged and secs_left:
                text += f" · {human_duration(secs_left)} left"
            self.battery_chip.setText(text)
            self.battery_chip.show()

        if self.temp_card is not None:
            self.temp_card.set_temps(snapshot.temps)

        if self.tray is not None:
            tip = f"CPU {snapshot.cpu_percent:.0f}%  ·  RAM {snapshot.mem_percent:.0f}%"
            if tip != self._tray_tip:
                self._tray_tip = tip
                self.tray.setToolTip(tip)
            self._update_tray_icon(snapshot.cpu_percent)
        if self.overlay is not None and self.overlay.isVisible():
            self.overlay.set_data(
                snapshot.cpu_percent,
                snapshot.mem_percent,
                f"↓ {human_speed(snapshot.net_down)}   ↑ {human_speed(snapshot.net_up)}",
            )

        stamp = datetime.now().strftime("%H:%M:%S")
        self.status_label.setText(
            f"Live · updated {stamp} · refresh {self._interval:g}s · tracking {len(snapshot.processes)} processes"
        )

    def _write_log(self, snapshot):
        # every tick lands in the log even if its frame gets coalesced away
        if self._log_file is None:
            return
        try:
            record = {
                "ts": snapshot.ts,
                "cpu": round(snapshot.cpu_percent, 1),
                "mem": round(snapshot.mem_percent, 1),
                "mem_used": snapshot.mem_used,
                "swap_used": snapshot.swap_used,
                "net_down": round(snapshot.net_down),
                "net_up": round(snapshot.net_up),
                "disk_read": round(snapshot.disk_read),
                "disk_write": round(snapshot.disk_write),
                "top_proc": snapshot.processes[0][1] if snapshot.processes else "",
            }
            self._log_file.write(json.dumps(record) + "\n")
        except (OSError, TypeError, ValueError):
            pass  # disk full, file rotated away... never kill the app over a log

    def _update_tray_icon(self, cpu_percent):
        # the tray icon IS the dashboard when the window is hidden: last 8
        # cpu samples as little bars. setIcon() is an ipc round-trip to the
        # shell, so it's capped at one update per 2s — nobody can read 1s
        # bars in a 24px icon anyway.
        self._tray_hist.append(cpu_percent)
        self._tray_paints += 1
        if self._tray_paints % 2:  # only every other tick
            return
        size = 24
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(theme.BG))
        painter = QPainter(pixmap)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.CPU))
        x = 1
        for value in self._tray_hist:
            h = max(2, int((size - 3) * value / 100.0))
            painter.drawRect(x, size - 1 - h, 2, h)
            x += 3
        painter.end()
        self.tray.setIcon(QIcon(pixmap))

    def _on_gpu(self, gpu):
        if self.gpu_gauge is None:
            return
        if gpu is None:
            if self._gpu_info is None:  # never had a reading
                self.gpu_sub.setText("no data")
            return
        self._gpu_name_full = gpu.name  # re-elide on resize
        self._gpu_info = gpu
        self.gpu_gauge.set_value(gpu.util)
        metrics = self.gpu_name.fontMetrics()
        elided = metrics.elidedText(gpu.name, Qt.TextElideMode.ElideRight, self.gpu_name.width())
        if self.gpu_name.text() != elided:
            self.gpu_name.setText(elided)
        if gpu.mem_total:
            stats = f"{human_bytes(gpu.mem_used)} / {human_bytes(gpu.mem_total)}"
        else:
            stats = human_bytes(gpu.mem_used)
        if gpu.temp:
            stats += f" · {gpu.temp:.0f}°C"
        self.gpu_sub.setText(stats)

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
            key = (info.used, info.total)
            if key != self._last_disk:  # disk numbers move slowly, skip the repaint
                self._last_disk = key
                self.disk_gauge.set_value(info.percent)
                self.disk_sub.setText(f"{human_bytes(info.used)} / {human_bytes(info.total)} · {info.fstype}")

    def _end_task(self, tree=False):
        pid = self.table.selected_pid()
        if pid is None:
            return
        row = self.table.currentRow()
        name_item = self.table.item(row, 1)
        name = name_item.text().lstrip("★ ") if name_item else str(pid)
        self._process_actions.end_task(pid, name, tree=tree)

    # --- process menu / details / watchlist ---

    def _process_menu(self, pid, menu):
        process_actions(self, pid, menu)

    def _show_detail(self, pid):
        if pid is None:
            return
        from .detail import DetailDialog  # local import keeps startup slim

        dialog = DetailDialog(pid, self)
        dialog.show()
        dialog.raise_()

    # --- alerts ---

    def _set_alerts_enabled(self, enabled):
        self._alerts_enabled = bool(enabled)
        QSettings("kxlt6969", "Pulse").setValue("alerts/enabled", self._alerts_enabled)

    def _show_about(self):
        QMessageBox.about(
            self,
            "About Pulse",
            f"Pulse {__version__}\n\n"
            "a task manager that doesn't hurt.\n\n"
            "python + pyside6 + psutil, everything drawn in code.\n"
            "MIT, do what you want.",
        )

    def _check_alerts(self):
        # paused means "stop nagging me", so alerts hold off while frozen
        if not self._alerts_enabled or self._paused or self._last_snapshot is None:
            return
        snap = self._last_snapshot
        settings = QSettings("kxlt6969", "Pulse")
        cpu_threshold = float(settings.value("alerts/cpu", 90))
        ram_threshold = float(settings.value("alerts/ram", 90))
        hold_seconds = float(settings.value("alerts/hold", 30))
        cooldown = max(60.0, hold_seconds)

        now = time.monotonic()
        for key, value, threshold in (
            ("cpu", snap.cpu_percent, cpu_threshold),
            ("ram", snap.mem_percent, ram_threshold),
        ):
            over, since, last_fired = self._alert_state.get(key, (False, 0.0, 0.0))
            if value >= threshold:
                if not over:
                    over, since = True, now
                if now - since >= hold_seconds and now - last_fired >= cooldown:
                    top = snap.processes[0][1] if snap.processes else "—"
                    if self.tray is not None:
                        self.tray.showMessage(
                            "Pulse",
                            f"{key.upper()} above {threshold:.0f}% for {hold_seconds:.0f}s (top: {top})",
                        )
                    last_fired = now
            else:
                over = False
            self._alert_state[key] = (over, since if value >= threshold else 0.0, last_fired)

    # --- settings dialog ---

    def _show_alerts_dialog(self):
        # alert thresholds live in settings, so this just opens that;
        # one dialog to maintain instead of two
        self._show_settings()

    def _show_settings(self):
        settings = QSettings("kxlt6969", "Pulse")
        dialog = QDialog(self)
        dialog.setWindowTitle("Pulse settings")
        layout = QVBoxLayout(dialog)

        def spin_row(label, key, default, lo, hi, suffix):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            spin = QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setDecimals(0)
            spin.setSuffix(suffix)
            spin.setValue(float(settings.value(key, default)))
            row.addWidget(spin)
            layout.addLayout(row)
            return spin

        cpu_spin = spin_row("CPU alert threshold", "alerts/cpu", 90, 10, 100, " %")
        ram_spin = spin_row("RAM alert threshold", "alerts/ram", 90, 10, 100, " %")
        hold_spin = spin_row("Hold before alert", "alerts/hold", 30, 10, 600, " s")
        scale_spin = spin_row("Network/disk scale", "charts/scale", self._net_scale, 1024, 1_000_000_000, " B/s")

        auto_box = QCheckBox("Auto-scale network/disk charts")
        auto_box.setChecked(self._autoscale)
        layout.addWidget(auto_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings.setValue("alerts/cpu", cpu_spin.value())
        settings.setValue("alerts/ram", ram_spin.value())
        settings.setValue("alerts/hold", hold_spin.value())
        settings.setValue("charts/scale", scale_spin.value())
        settings.setValue("charts/autoscale", auto_box.isChecked())
        self._net_scale = max(1024.0, scale_spin.value())
        self._autoscale = auto_box.isChecked()

    def _toggle_pause(self, paused):
        self._paused = bool(paused)
        if not self._paused and self._last_snapshot is not None:
            # repaint straight from the stored frame; skip the log so the
            # same sample doesn't land twice
            self._paint_snapshot(self._last_snapshot)

    # --- helpers for the snapshot handler ---

    # feed key -> (chart attribute, series name inside that chart)
    _CHART_FEEDS = {
        "cpu": ("cpu_chart", "cpu"),
        "net_down": ("net_chart", "down"),
        "net_up": ("net_chart", "up"),
        "disk_read": ("disk_chart", "read"),
        "disk_write": ("disk_chart", "write"),
    }

    def _feed_chart(self, key, value):
        history = self._history.get(key)
        if history is None:
            history = self._history[key] = deque(maxlen=60)
        history.append(value)
        chart_name, series = self._CHART_FEEDS[key]
        chart = getattr(self, chart_name, None)
        if chart is not None:
            chart.push(series, list(history))

    def _install_shortcuts(self):
        # space freezes, ctrl+f jumps to the filter, delete ends the task
        pause = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        pause.activated.connect(lambda: self._toggle_pause(not self._paused))

        find = QShortcut(QKeySequence("Ctrl+F"), self)
        find.activated.connect(self._focus_filter)

        copy = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        copy.activated.connect(self.table.copy_visible_as_csv)

        kill = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        kill.activated.connect(lambda: self._end_task(tree=False))

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._escape)

    def _focus_filter(self):
        self.filter_input.setFocus()
        self.filter_input.selectAll()

    def _escape(self):
        if self.filter_input.text():
            self.filter_input.clear()
        else:
            self.table.clearSelection()
            self.end_btn.setEnabled(False)

    # --- settings persistence ---

    def restore_settings(self):
        settings = QSettings("kxlt6969", "Pulse")
        scale = settings.value("charts/scale", 0, type=float) or 0
        if scale >= 1024:
            self._net_scale = scale
        self._autoscale = bool(settings.value("charts/autoscale", False, type=bool))
        self._watched = {int(pid) for pid in settings.value("watchlist", []) or []}
        self._alerts_enabled = bool(settings.value("alerts/enabled", True, type=bool))
        geometry = settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.gpu_gauge is not None and self._gpu_name_full:
            metrics = self.gpu_name.fontMetrics()
            self.gpu_name.setText(
                metrics.elidedText(self._gpu_name_full, Qt.TextElideMode.ElideRight, self.gpu_name.width())
            )

    def closeEvent(self, event):
        # close button hides to the tray when there is one, quit lives in the tray menu
        if self.tray is not None and not self._quitting:
            event.ignore()
            self.hide()
            if not self._tray_notified:
                self.tray.showMessage("Pulse", "Still running in the tray — right-click the tray icon to quit.")
                self._tray_notified = True
            return
        self._worker.stop()
        self._gpu_worker.stop()
        if self._log_file is not None:
            self._log_file.close()
        settings = QSettings("kxlt6969", "Pulse")
        settings.setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)
