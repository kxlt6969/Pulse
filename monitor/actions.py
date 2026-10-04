# the destructive process actions (kill, priority, affinity). they live
# apart from app.py because they're the only bits of the ui that reach out
# and change the system, so they get their own guardrails: every action
# confirms first, and every failure lands in a message box, not a traceback.

import sys

import psutil
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
)


def confirm(parent, title, body):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(body)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    return box.exec() == QMessageBox.StandardButton.Yes


class ProcessActions(QObject):
    # failed = (pid, what, why) after an action couldn't complete
    failed = Signal(int, str, str)
    done = Signal(int, str)  # pid, what — lets the window show a status message

    def __init__(self, parent):
        super().__init__(parent)
        self._win = parent

    # --- kill ---

    def end_task(self, pid, name, tree=False):
        kind = "process tree" if tree else "process"
        if not confirm(
            self._win,
            "End task",
            f"Terminate {kind} “{name}” (PID {pid})?",
        ):
            return
        try:
            proc = psutil.Process(pid)
            if tree:
                children = proc.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                proc.terminate()
                psutil.wait_procs(children, timeout=3)
            else:
                proc.terminate()
            self.done.emit(pid, "terminate")
        except psutil.NoSuchProcess:
            self.done.emit(pid, "already-gone")
        except Exception as exc:
            self.failed.emit(pid, "end task", str(exc))

    # --- priority ---

    def set_priority(self, pid, value):
        try:
            psutil.Process(pid).nice(value)
            self.done.emit(pid, "priority")
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError) as exc:
            self.failed.emit(pid, "priority", str(exc))

    # --- affinity ---

    def set_affinity_dialog(self, pid):
        try:
            proc = psutil.Process(pid)
            current = proc.cpu_affinity()
            cpus = psutil.cpu_count(logical=True) or 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError) as exc:
            self.failed.emit(pid, "affinity", str(exc))
            return

        dialog = QDialog(self._win)
        dialog.setWindowTitle(f"CPU affinity — PID {pid}")
        layout = QVBoxLayout(dialog)
        row = QHBoxLayout()
        boxes = []
        for i in range(cpus):
            box = QCheckBox(f"CPU {i}")
            box.setChecked(i in current)
            boxes.append((i, box))
            row.addWidget(box)
        layout.addLayout(row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        picked = [i for i, box in boxes if box.isChecked()]
        if not picked:
            return
        try:
            proc.cpu_affinity(picked)
            self.done.emit(pid, "affinity")
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError) as exc:
            self.failed.emit(pid, "affinity", str(exc))

    # --- wiring ---

    def connect_status(self, window):
        self.done.connect(lambda pid, what: window.statusBar().showMessage(_STATUS.get(what, what), 4000))
        self.failed.connect(self._on_failed)

    def _on_failed(self, pid, what, why):
        QMessageBox.warning(self._win, what, f"Could not do that to PID {pid}:\n{why}")


_STATUS = {
    "terminate": "Terminate signal sent",
    "already-gone": "Process already exited",
    "priority": "Priority updated",
    "affinity": "CPU affinity updated",
}


# windows-only priority classes; psutil doesn't export them elsewhere, so
# guard the import or linux/mac would die the moment this module loads
if sys.platform == "win32":
    _PRIORITY_LEVELS = (
        ("Realtime", psutil.REALTIME_PRIORITY_CLASS),
        ("High", psutil.HIGH_PRIORITY_CLASS),
        ("Above normal", psutil.ABOVE_NORMAL_PRIORITY_CLASS),
        ("Normal", psutil.NORMAL_PRIORITY_CLASS),
        ("Below normal", psutil.BELOW_NORMAL_PRIORITY_CLASS),
        ("Idle", psutil.IDLE_PRIORITY_CLASS),
    )
else:
    _PRIORITY_LEVELS = ()


def process_actions(window, pid, menu):
    """Fill a context menu with the process actions for `pid`."""
    actions = getattr(window, "_process_actions", None)
    if actions is None:
        return
    row = window.table.currentRow()
    name_item = window.table.item(row, 1) if row >= 0 else None
    name = name_item.text().lstrip("★ ") if name_item else str(pid)

    end_action = menu.addAction("End task")
    end_action.triggered.connect(lambda: actions.end_task(pid, name))
    tree_action = menu.addAction("End process tree")
    tree_action.triggered.connect(lambda: actions.end_task(pid, name, tree=True))
    if _PRIORITY_LEVELS:  # empty on non-windows, don't ship a dead submenu
        menu.addSeparator()
        prio_menu = menu.addMenu("Set priority")
        for label, value in _PRIORITY_LEVELS:
            action = prio_menu.addAction(label)
            action.triggered.connect(lambda _=False, v=value: actions.set_priority(pid, v))
    aff_action = menu.addAction("Set affinity…")
    aff_action.triggered.connect(lambda: actions.set_affinity_dialog(pid))
