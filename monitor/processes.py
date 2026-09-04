from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

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


class ProcessTable(QTableWidget):
    HEADERS = ["PID", "PROCESS", "CPU %", "MEMORY"]

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

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSortIndicator(2, Qt.SortOrder.DescendingOrder)

    def update_rows(self, rows):
        # keep the user's sort across refreshes
        header = self.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()

        self.setSortingEnabled(False)  # required while inserting items
        self.setRowCount(len(rows))
        for index, (pid, name, cpu, memory) in enumerate(rows):
            pid_item = _NumericItem(str(pid))
            pid_item.setData(Qt.ItemDataRole.UserRole, pid)
            pid_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            name_item = QTableWidgetItem(name)

            cpu_item = _NumericItem(f"{cpu:.1f}")
            cpu_item.setData(Qt.ItemDataRole.UserRole, cpu)
            cpu_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if cpu >= 75.0:
                cpu_item.setForeground(QColor(theme.DANGER))
            elif cpu >= 35.0:
                cpu_item.setForeground(QColor(theme.WARN))

            mem_item = _NumericItem(human_bytes(memory))
            mem_item.setData(Qt.ItemDataRole.UserRole, memory)
            mem_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.setItem(index, 0, pid_item)
            self.setItem(index, 1, name_item)
            self.setItem(index, 2, cpu_item)
            self.setItem(index, 3, mem_item)

        self.setSortingEnabled(True)
        self.sortItems(sort_column, sort_order)

    def selected_pid(self):
        row = self.currentRow()
        if row < 0:
            return None
        item = self.item(row, 0)
        return int(item.text()) if item else None
