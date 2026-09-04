# All the psutil polling lives here on its own thread so the UI never blocks.
# The process scan is by far the slowest call, so it belongs on this thread too.

import time
from dataclasses import dataclass

import psutil
from PySide6.QtCore import QThread, Signal


@dataclass
class DiskInfo:
    mount: str
    percent: float
    used: int
    total: int
    fstype: str


@dataclass
class Snapshot:
    ts: float
    cpu_percent: float
    cpu_per_core: list[float]
    cpu_freq: float | None
    cores_logical: int
    cores_physical: int | None
    mem_total: int
    mem_used: int
    mem_percent: float
    swap_total: int
    swap_used: int
    swap_percent: float
    disks: list[DiskInfo]
    net_down: float  # bytes per second
    net_up: float
    net_total_down: int
    net_total_up: int
    processes: list[tuple[int, str, float, int]]  # (pid, name, cpu %, rss)
    battery: tuple[float, bool, int | None] | None  # (percent, plugged, secs_left)
    uptime: float


def _partitions():
    disks = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or part.fstype == "":
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        if usage.total > 0:
            disks.append(DiskInfo(part.mountpoint, usage.percent, usage.used, usage.total, part.fstype))
    return disks


def _battery():
    getter = getattr(psutil, "sensors_battery", None)
    if getter is None:  # not every platform has it
        return None
    try:
        batt = getter()
    except Exception:
        return None
    if batt is None:
        return None
    secs = batt.secsleft
    if secs is not None and secs < 0:  # POWER_TIME_UNKNOWN / UNLIMITED
        secs = None
    return (batt.percent, bool(batt.power_plugged), secs)


def _processes(limit, logical_cores):
    rows = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        info = proc.info
        pid = info["pid"]
        name = info["name"] or "unknown"
        if pid == 0 or name.lower() == "system idle process":
            continue
        cpu = info["cpu_percent"] or 0.0
        cpu = cpu / logical_cores if logical_cores else cpu  # 100% = all cores, like task manager
        mem = info["memory_info"].rss if info["memory_info"] else 0
        rows.append((pid, name[:48], cpu, mem))
    rows.sort(key=lambda row: (row[2], row[3]), reverse=True)
    return rows[:limit]


class MonitorWorker(QThread):
    snapshot_ready = Signal(object)

    def __init__(self, interval=1.0, process_limit=25, parent=None):
        super().__init__(parent)
        self.interval = max(0.25, float(interval))
        self.process_limit = process_limit
        self._stop = False

    def run(self):
        # psutil cpu% needs two samples, the first call always returns 0.
        # Prime everything once so the first real tick is meaningful.
        psutil.cpu_percent(percpu=False)
        psutil.cpu_percent(percpu=True)
        list(psutil.process_iter(["cpu_percent"]))

        cores_logical = psutil.cpu_count(logical=True) or 1
        cores_physical = psutil.cpu_count(logical=False)
        prev_net = psutil.net_io_counters()
        prev_time = time.monotonic()

        while not self._stop:
            self.msleep(int(self.interval * 1000))
            if self._stop:
                break

            now = time.monotonic()
            elapsed = max(1e-6, now - prev_time)
            try:
                net = psutil.net_io_counters()
            except Exception:
                net = prev_net
            # max() guards against counter resets making the delta negative
            down = max(0.0, (net.bytes_recv - prev_net.bytes_recv) / elapsed)
            up = max(0.0, (net.bytes_sent - prev_net.bytes_sent) / elapsed)
            prev_net, prev_time = net, now

            try:
                snapshot = self._collect(down, up, net, cores_logical, cores_physical)
            except Exception as exc:  # don't let one bad tick kill the loop
                print(f"[pulse] collection error: {exc!r}")
                continue

            self.snapshot_ready.emit(snapshot)

    def _collect(self, down, up, net, cores_logical, cores_physical):
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        try:
            freq = psutil.cpu_freq()
            cpu_freq = freq.current if freq else None
        except Exception:
            cpu_freq = None

        return Snapshot(
            ts=time.time(),
            cpu_percent=psutil.cpu_percent(percpu=False),
            cpu_per_core=psutil.cpu_percent(percpu=True),
            cpu_freq=cpu_freq,
            cores_logical=cores_logical,
            cores_physical=cores_physical,
            mem_total=mem.total,
            mem_used=mem.used,
            mem_percent=mem.percent,
            swap_total=swap.total,
            swap_used=swap.used,
            swap_percent=swap.percent,
            disks=_partitions(),
            net_down=down,
            net_up=up,
            net_total_down=net.bytes_recv,
            net_total_up=net.bytes_sent,
            processes=_processes(self.process_limit, cores_logical),
            battery=_battery(),
            uptime=time.time() - psutil.boot_time(),
        )

    def stop(self):
        self._stop = True
        self.wait(int(self.interval * 1000) + 2500)
