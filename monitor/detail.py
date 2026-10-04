import time

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from . import theme
from .fmt import human_bytes, human_duration
from .widgets import Sparkline

# windows priority classes -> readable names (psutil also exposes these as
# constants on other platforms, but they're only really meaningful on win32)
_PRIORITY_NAMES = {}


def _priority_text(raw):
    if not _PRIORITY_NAMES:
        for attr, label in (
            ("REALTIME_PRIORITY_CLASS", "realtime"),
            ("HIGH_PRIORITY_CLASS", "high"),
            ("ABOVE_NORMAL_PRIORITY_CLASS", "above normal"),
            ("NORMAL_PRIORITY_CLASS", "normal"),
            ("BELOW_NORMAL_PRIORITY_CLASS", "below normal"),
            ("IDLE_PRIORITY_CLASS", "idle"),
        ):
            value = getattr(psutil, attr, None)
            if value is not None:
                _PRIORITY_NAMES[value] = label
    return _PRIORITY_NAMES.get(raw, str(raw))


class DetailDialog(QDialog):
    """Live per-process popup. Polls just the one process, once a second."""

    def __init__(self, pid, parent=None):
        super().__init__(parent)
        self._pid = int(pid)
        self.setWindowTitle(f"Pulse — PID {self._pid}")
        self.setModal(False)
        self.setMinimumWidth(470)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        self.title = QLabel(f"PID {self._pid}")
        self.title.setObjectName("appTitle")
        self.status_chip = QLabel("…")
        self.status_chip.setObjectName("chip")
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.status_chip)
        root.addLayout(head)

        self.spark = Sparkline("CPU")
        root.addWidget(self.spark)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(18)
        metrics.setVerticalSpacing(4)
        self.cpu_label = QLabel("—")
        self.cpu_label.setObjectName("appTitle")
        self.mem_label = QLabel("—")
        self.mem_label.setObjectName("appTitle")
        self.user_label = QLabel("—")
        self.user_label.setObjectName("appTitle")
        for column, (title, widget) in enumerate(
            (("CPU %", self.cpu_label), ("MEMORY", self.mem_label), ("USER", self.user_label))
        ):
            box = QVBoxLayout()
            caption = QLabel(title)
            caption.setObjectName("cardTitle")
            box.addWidget(caption)
            box.addWidget(widget)
            metrics.addLayout(box, 0, column)
        root.addLayout(metrics)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {theme.CARD_BORDER}; background: {theme.CARD_BORDER};")
        root.addWidget(line)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(4)
        root.addLayout(self.grid)
        self._rows = {}  # key -> (left label, right label), built on first sight

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.end_button = QPushButton("End task")
        self.end_button.setObjectName("endTask")
        self.end_button.clicked.connect(self._end)
        buttons.addWidget(self.end_button)
        root.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self._refresh()
        self._timer.start()

    def _refresh(self):
        try:
            proc = psutil.Process(self._pid)
            with proc.oneshot():
                name = proc.name()
                cpu = proc.cpu_percent() / (psutil.cpu_count(logical=True) or 1)
                mem = proc.memory_info()
                create_time = proc.create_time()
                status = str(proc.status())
                ppid = proc.ppid()
                threads = proc.num_threads()
                try:
                    cmdline = " ".join(proc.cmdline())
                except Exception:
                    cmdline = ""
                try:
                    exe = proc.exe()
                except Exception:
                    exe = ""
                try:
                    user = proc.username()
                except Exception:
                    user = "—"
                try:
                    priority = _priority_text(proc.nice())
                except Exception:
                    priority = "—"
                try:
                    affinity = len(proc.cpu_affinity())
                except Exception:
                    affinity = None

            self.spark.push(cpu)
            self.cpu_label.setText(f"{cpu:.1f}%")
            self.mem_label.setText(human_bytes(mem.rss))
            self.user_label.setText(user)
            self.status_chip.setText(status)

            uptime = max(0, int(_now() - create_time))
            rows = [
                ("name", name),
                ("pid", str(self._pid)),
                ("parent pid", str(ppid)),
                ("user", user),
                ("started", f"{human_duration(uptime)} ago"),
                ("threads", str(threads)),
                ("priority", priority),
            ]
            if affinity is not None:
                rows.append(("cpu affinity", f"{affinity} of {psutil.cpu_count(logical=True)} cores"))
            if exe:
                rows.append(("exe", exe))
            if cmdline:
                rows.append(("command line", cmdline))

            # labels are created once per key and only their text updates
            for index, (key, value) in enumerate(rows):
                pair = self._rows.get(key)
                if pair is None:
                    left = QLabel(key)
                    left.setObjectName("cardSub")
                    right = QLabel(value)
                    right.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    right.setWordWrap(True)
                    self._rows[key] = (left, right)
                    self.grid.addWidget(left, index, 0)
                    self.grid.addWidget(right, index, 1)
                else:
                    left, right = pair
                    if right.text() != value:
                        right.setText(value)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            self.status_chip.setText("gone")
            self._timer.stop()
            self.end_button.setEnabled(False)
            self.spark.push(0.0)
        except Exception:
            self.status_chip.setText("error")

    def _end(self):
        try:
            psutil.Process(self._pid).terminate()
            self.status_chip.setText("terminating…")
        except psutil.NoSuchProcess:
            self.status_chip.setText("gone")
        except Exception as exc:
            self.status_chip.setText(f"failed: {exc}")


def _now():
    return time.time() - psutil.boot_time()
