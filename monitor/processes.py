from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
)

from . import theme
from .fmt import human_bytes


class _NumericItem(QTableWidgetItem):
    # sorts by the raw number stashed in UserRole, not the display string
    def __lt__(self, other):
        mine = self.data(Qt.ItemDataRole.UserRole)
        theirs = other.data(Qt.ItemDataRole.UserRole)
        if mine is not None and theirs is not None:
            return float(mine) < float(theirs)
        return super().__lt__(other)


def _parse_mem(text):
    # '100mb' / '2g' / '512k' -> bytes; None if not a memory token
    text = text.lower()
    for suffix, factor in (("gb", 2**30), ("mb", 2**20), ("kb", 2**10), ("g", 2**30), ("m", 2**20), ("k", 2**10)):
        if text.endswith(suffix):
            try:
                return int(float(text[: -len(suffix)]) * factor)
            except ValueError:
                return None
    return None


def _matches(row, text):
    """Filter mini-language: plain text matches name/pid, or cpu>50,
    cpu<10, mem>100mb, mem<2g. Everything else falls back to substring."""
    pid, name, cpu, memory = row[0], row[1].lower(), row[2], row[3]
    for term in text.split():
        if ">" in term or "<" in term:
            op_index = term.find(">")
            if op_index == -1:
                op_index = term.find("<")
            field, rest = term[:op_index], term[op_index:]
            if field == "cpu":
                try:
                    value = float(rest[1:])
                except ValueError:
                    return False
                if rest.startswith(">") and not cpu >= value:
                    return False
                if rest.startswith("<") and not cpu < value:
                    return False
            elif field == "mem":
                bytes_value = _parse_mem(rest[1:])
                if bytes_value is None:
                    return False
                if rest.startswith(">") and not memory >= bytes_value:
                    return False
                if rest.startswith("<") and not memory < bytes_value:
                    return False
            else:
                return False
        elif term in name or term in str(pid):
            continue
        else:
            return False
    return True


class ProcessTable(QTableWidget):
    HEADERS = ["PID", "PROCESS", "CPU %", "MEMORY"]

    open_details = Signal(int)  # pid, via double-click or context menu
    context_menu = Signal(int, object)  # pid, QMenu the caller can extend
    watch_changed = Signal(list)  # the watchlist changed, persist it

    def __init__(self, parent=None):
        super().__init__(0, len(self.HEADERS), parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(30)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setSortingEnabled(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSortIndicator(2, Qt.SortOrder.DescendingOrder)
        self._filter = ""
        self._watched = set()

        self.customContextMenuRequested.connect(self._menu_requested)
        self.itemDoubleClicked.connect(self._double_clicked)

    def watch_pid(self, pid):
        if pid is not None:
            self._watched.add(int(pid))
            self.watch_changed.emit(self.watched_pids())

    def unwatch_pid(self, pid):
        if int(pid) in self._watched:
            self._watched.discard(int(pid))
            self.watch_changed.emit(self.watched_pids())

    def is_watched(self, pid):
        return int(pid) in self._watched

    def watched_pids(self):
        return sorted(self._watched)

    def set_filter(self, text):
        self._filter = (text or "").strip().lower()

    def update_rows(self, rows):
        if self._filter:
            rows = [row for row in rows if _matches(row, self._filter)]
        if self._watched:
            # pinned processes jump the queue, so they're always on screen
            rows = sorted(rows, key=lambda r: 0 if int(r[0]) in self._watched else 1)

        # keep the user's sort across refreshes
        header = self.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()

        self.setSortingEnabled(False)
        self.setUpdatesEnabled(False)  # one repaint, not one per cell

        if self.rowCount() != len(rows):
            self.setRowCount(len(rows))

        for index, row in enumerate(rows):
            pid, name, cpu, memory = row[0], row[1], row[2], row[3]
            watched = int(pid) in self._watched

            pid_item = self.item(index, 0)
            if pid_item is None:
                pid_item = _NumericItem()
                pid_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(index, 0, pid_item)
            pid_item.setText(str(pid))
            pid_item.setData(Qt.ItemDataRole.UserRole, pid)

            name_item = self.item(index, 1)
            if name_item is None:
                name_item = QTableWidgetItem()
                self.setItem(index, 1, name_item)
            shown = f"★ {name}" if watched else name
            if name_item.text() != shown:
                name_item.setText(shown)

            cpu_item = self.item(index, 2)
            if cpu_item is None:
                cpu_item = _NumericItem()
                cpu_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(index, 2, cpu_item)
            cpu_item.setText(f"{cpu:.1f}")
            cpu_item.setData(Qt.ItemDataRole.UserRole, cpu)
            if cpu >= 75.0:
                cpu_item.setForeground(QColor(theme.DANGER))
            elif cpu >= 35.0:
                cpu_item.setForeground(QColor(theme.WARN))
            else:
                cpu_item.setData(Qt.ItemDataRole.ForegroundRole, None)

            mem_item = self.item(index, 3)
            if mem_item is None:
                mem_item = _NumericItem()
                mem_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.setItem(index, 3, mem_item)
            mem_item.setText(human_bytes(memory))
            mem_item.setData(Qt.ItemDataRole.UserRole, memory)

        self.setUpdatesEnabled(True)
        self.setSortingEnabled(True)
        self.sortItems(sort_column, sort_order)

    def selected_pid(self):
        row = self.currentRow()
        if row < 0:
            return None
        item = self.item(row, 0)
        return int(item.text()) if item else None

    def copy_visible_as_csv(self):
        # for pasting into a bug report or a spreadsheet
        lines = [",".join(self.HEADERS)]
        for row in range(self.rowCount()):
            cells = [self.item(row, col).text() for col in range(4) if self.item(row, col)]
            if cells:
                lines.append(",".join(cells))
        QGuiApplication.clipboard().setText("\n".join(lines))

    # --- interactions ---

    def _double_clicked(self, item):
        pid_item = self.item(item.row(), 0)
        if pid_item is not None:
            self.open_details.emit(int(pid_item.text()))

    def _menu_requested(self, pos):
        row = self.rowAt(pos.y())
        if row < 0:
            return
        pid_item = self.item(row, 0)
        if pid_item is None:
            return
        self.selectRow(row)
        pid = int(pid_item.text())
        menu = QMenu(self)
        watch_action = menu.addAction(
            "Unwatch" if self.is_watched(pid) else "Watch this process"
        )
        watch_action.triggered.connect(
            lambda: self.unwatch_pid(pid) if self.is_watched(pid) else self.watch_pid(pid)
        )
        details_action = menu.addAction("Details…")
        details_action.triggered.connect(lambda: self.open_details.emit(pid))
        menu.addSeparator()
        self.context_menu.emit(pid, menu)  # app adds priority/affinity/end tree
        menu.exec(self.viewport().mapToGlobal(pos))
