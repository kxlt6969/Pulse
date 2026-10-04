# All the psutil polling lives here on its own thread so the UI never blocks.
# The process scan is by far the slowest call, so it belongs on this thread too.
#
# GPU support is two paths, best one wins:
#   - nvidia: NVML via pynvml (util, vram, temp)
#   - windows: GPU Engine / GPU Adapter Memory perf counters via powershell,
#     name + total vram from the registry (AdapterRAM lies above 4GB, the
#     driver class key doesn't). works for AMD/Intel. no temps on this path.
#
# The counter query takes a couple of seconds, so the GPU gets its own worker
# thread; running it inline would stall the 1s psutil loop every few ticks.

import subprocess
import sys
import time
from dataclasses import dataclass

import psutil
from PySide6.QtCore import QThread, Signal

try:
    import pynvml
except ImportError:
    pynvml = None

# one powershell round-trip for both counters, about half the cost of two calls
_GPU_PS = (
    "$c=(Get-Counter '\\GPU Engine(*)\\Utilization Percentage','\\GPU Adapter Memory(*)\\Dedicated Usage'"
    " -ErrorAction SilentlyContinue).CounterSamples;"
    "$u=0.0; $m=0.0;"
    "foreach($s in $c){"
    " if($s.Path -match 'utilization percentage' -and $s.CookedValue -gt 0){$u+=$s.CookedValue};"
    " if($s.Path -match 'dedicated usage'){$m+=$s.CookedValue} };"
    "'UTIL='+[math]::Round($u,1); 'MEM='+[math]::Round($m)"
)


@dataclass(frozen=True, slots=True)
class DiskInfo:
    mount: str
    percent: float
    used: int
    total: int
    fstype: str


@dataclass(frozen=True, slots=True)
class GpuInfo:
    name: str
    util: float
    mem_used: int
    mem_total: int
    temp: float | None


@dataclass(frozen=True, slots=True)
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
    mem_cached: int
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
    temps: list[tuple[str, float, float | None, float | None]] | None = None
    disk_read: float = 0.0  # bytes per second, whole-disk, filled by _snapshot
    disk_write: float = 0.0


def _registry_gpu():
    # (name, vram bytes) of the biggest display adapter, or None
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    best = None
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return None
    with root:
        for i in range(12):
            try:
                sub = winreg.EnumKey(root, i)
            except OSError:
                break
            try:
                with winreg.OpenKey(root, sub) as key:
                    name = winreg.QueryValueEx(key, "DriverDesc")[0]
                    try:
                        size = int(winreg.QueryValueEx(key, "HardwareInformation.qwMemorySize")[0])
                    except OSError:
                        size = 0
            except OSError:
                continue
            if not name or "microsoft basic" in name.lower():
                continue
            if best is None or size > best[1]:
                best = (str(name), size)
    return best


def _windows_gpu_counters(should_stop=None):
    # (util %, dedicated vram bytes) from the perf counters, or None
    try:
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _GPU_PS],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=flags,
        )
    except Exception:
        return None
    # powershell takes a second or two to spin up, so wait in small slices
    # and kill it if we're shutting down. a blocking wait here used to stall
    # quit for up to ~15s.
    stdout = ""
    deadline = time.monotonic() + 12.0
    while True:
        try:
            stdout, _ = proc.communicate(timeout=0.25)
            break
        except subprocess.TimeoutExpired:
            if (should_stop and should_stop()) or time.monotonic() > deadline:
                proc.kill()
                return None
    util = mem = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("UTIL="):
            try:
                util = float(line[5:])
            except ValueError:
                pass
        elif line.startswith("MEM="):
            try:
                mem = float(line[4:])
            except ValueError:
                pass
    if util is None or mem is None:
        return None
    return (util, mem)


# mounts that took suspiciously long to stat, skip them for a while
_slow_mounts = {}

# whole-disk io deltas, kept across ticks (None until the first sample)
_disk_io_prev = None


def _partitions():
    disks = []
    now = time.monotonic()
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or part.fstype == "":
            continue
        if _slow_mounts.get(part.mountpoint, 0.0) > now:
            continue
        started = time.monotonic()
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        if time.monotonic() - started > 1.0:
            # dead network drive or similar — don't stall every single tick
            _slow_mounts[part.mountpoint] = now + 60.0
            continue
        if usage.total > 0:
            disks.append(DiskInfo(part.mountpoint, usage.percent, usage.used, usage.total, part.fstype))
    return disks


# battery rarely changes, don't query it every tick
_BATTERY_SECS = 15

# same story for swap (see _snapshot for why)
_SWAP_SECS = 15
_swap_poll = None

# cpu_freq() is a wmi trip on windows and clock speed doesn't need 1hz
# resolution; disk usage changes even slower
_FREQ_SECS = 3.0
_freq_poll = None
_DISKS_SECS = 5.0
_disks_poll = None


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
        # order matters here. the first process scan runs before anything is
        # measured (the table needs rows on the first paint, and the scan
        # would poison the cpu sample). then the cpu counters are primed and
        # a full interval is slept BEFORE the first real sample: sampling
        # immediately after priming measured over the app's own startup
        # burst, and the gauge spiked into the 80s for a second.
        cores_logical = psutil.cpu_count(logical=True) or 1
        cores_physical = psutil.cpu_count(logical=False)

        last_scan = 0.0
        scan_every = 2.0
        cached_rows = None
        scan_started = time.monotonic()
        try:
            cached_rows = _processes(self.process_limit, cores_logical)
        except Exception as exc:
            print(f"[pulse] process scan error: {exc!r}")
        scan_cost = time.monotonic() - scan_started
        last_scan = scan_started
        # a scan that costs 50ms can afford to run often; one that costs
        # half a second shouldn't — spend ~1/10th of the cadence on
        # scanning, whichever machine we're on
        scan_every = min(15.0, max(2.0, scan_cost * 10))

        psutil.cpu_percent(percpu=False)
        psutil.cpu_percent(percpu=True)
        prev_net = psutil.net_io_counters()
        prev_time = time.monotonic()
        last_battery = time.monotonic()
        battery = _battery()
        temps = _temps()

        self.msleep(int(self.interval * 1000))
        if self._stop:
            return

        while not self._stop:
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

            if now - last_scan >= scan_every:
                scan_started = time.monotonic()
                try:
                    cached_rows = _processes(self.process_limit, cores_logical)
                    last_scan = now
                except Exception as exc:
                    print(f"[pulse] process scan error: {exc!r}")
                    # keep last good rows on failure
                scan_cost = time.monotonic() - scan_started
                scan_every = min(15.0, max(2.0, scan_cost * 10))
            try:
                snapshot = _snapshot(
                    down,
                    up,
                    net,
                    cores_logical,
                    cores_physical,
                    battery,
                    self.process_limit,
                    temps,
                    process_rows=cached_rows,
                )
            except Exception as exc:  # don't let one bad tick kill the loop
                print(f"[pulse] collection error: {exc!r}")
                snapshot = None
            if snapshot is not None:
                self.snapshot_ready.emit(snapshot)

            spent = time.monotonic() - now
            self.msleep(max(0, int((self.interval - spent) * 1000)))

            if self._stop:
                break
            if now - last_battery >= _BATTERY_SECS:
                last_battery = now
                battery = _battery()
                temps = _temps()

    def stop(self):
        self._stop = True
        if not self.wait(int(self.interval * 1000) + 2500):
            # a big process scan can outrun the wait; better a hard stop at
            # quit than the window hanging on the way down
            self.terminate()
            self.wait(500)


def _temps():
    # sensors_temperatures doesn't exist on every platform; on windows it
    # raises NotImplementedError fast, so this is a cheap call either way
    try:
        return psutil.sensors_temperatures()
    except Exception:
        return None


def _snapshot(
    down,
    up,
    net,
    cores_logical,
    cores_physical,
    battery,
    process_limit,
    temps=None,
    process_rows=None,
):
    global _disk_io_prev
    disk_read = disk_write = 0.0
    try:
        io = psutil.disk_io_counters()
    except Exception:
        io = None
    if io is not None and _disk_io_prev is not None:
        prev_read, prev_write, prev_time = _disk_io_prev
        elapsed = max(1e-6, time.monotonic() - prev_time)
        disk_read = max(0.0, (io.read_bytes - prev_read) / elapsed)
        disk_write = max(0.0, (io.write_bytes - prev_write) / elapsed)
    if io is not None:
        _disk_io_prev = (io.read_bytes, io.write_bytes, time.monotonic())

    mem = psutil.virtual_memory()
    now = time.monotonic()

    # swap_memory() is stupidly expensive on windows (GetPerformanceInfo,
    # ~180ms here) and the total basically never changes, so poll it rarely
    # and interpolate usage from total-memory movement in between. not
    # perfect (page-outs while ram is flat get missed) but invisible at
    # the resolution anyone actually watches swap at.
    global _swap_poll
    if _swap_poll is not None and now - _swap_poll[0] < _SWAP_SECS:
        polled_at, prev_swap, prev_mem_used = _swap_poll
        used = prev_swap.used + (mem.used - prev_mem_used)
        swap_total = prev_swap.total
        swap_used = min(max(used, 0), swap_total)
    else:
        fresh = psutil.swap_memory()
        _swap_poll = (now, fresh, mem.used)
        swap_total = fresh.total
        swap_used = fresh.used
    swap_percent = swap_used / swap_total * 100 if swap_total else 0.0

    global _freq_poll
    if _freq_poll is not None and now - _freq_poll[0] < _FREQ_SECS:
        cpu_freq = _freq_poll[1]
    else:
        try:
            freq = psutil.cpu_freq()
            cpu_freq = freq.current if freq else None
        except Exception:
            cpu_freq = None
        _freq_poll = (now, cpu_freq)

    global _disks_poll
    if _disks_poll is not None and now - _disks_poll[0] < _DISKS_SECS:
        disks = _disks_poll[1]
    else:
        disks = _partitions()
        _disks_poll = (now, disks)
    # cached/buffers is RAM the kernel is just holding onto, not really used
    cached = int(getattr(mem, "cached", 0) or 0) + int(getattr(mem, "buffers", 0) or 0)

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
        mem_cached=cached,
        swap_total=swap_total,
        swap_used=swap_used,
        swap_percent=swap_percent,
        disks=disks,
        net_down=down,
        net_up=up,
        net_total_down=net.bytes_recv,
        net_total_up=net.bytes_sent,
        processes=(
            _processes(process_limit, cores_logical)
            if process_rows is None
            else process_rows
        ),
        battery=battery,
        uptime=time.time() - psutil.boot_time(),
        temps=temps,
        disk_read=disk_read,
        disk_write=disk_write,
    )


def collect_snapshot(process_limit=25, sample_seconds=0.5):
    """one-shot snapshot without a thread, for --json and tests."""
    # prime the cpu counters (first call always returns 0) and run one
    # throwaway process scan so per-process cpu% has a baseline, then
    # measure over a short window so the numbers mean something
    psutil.cpu_percent(percpu=False)
    psutil.cpu_percent(percpu=True)
    try:
        _processes(process_limit, psutil.cpu_count(logical=True) or 1)
    except Exception:
        pass
    prev_net = psutil.net_io_counters()
    prev_time = time.monotonic()
    time.sleep(max(0.05, sample_seconds))
    now = time.monotonic()
    elapsed = max(1e-6, now - prev_time)
    net = psutil.net_io_counters()
    down = max(0.0, (net.bytes_recv - prev_net.bytes_recv) / elapsed)
    up = max(0.0, (net.bytes_sent - prev_net.bytes_sent) / elapsed)
    cores_logical = psutil.cpu_count(logical=True) or 1
    cores_physical = psutil.cpu_count(logical=False)
    battery = _battery()
    return _snapshot(
        down, up, net, cores_logical, cores_physical, battery,
        process_limit, _temps(),
    )


class GpuWorker(QThread):
    # slow gpu queries, separate thread so they can't stall the psutil loop

    gpu_ready = Signal(object)  # GpuInfo, or None once after repeated failures

    def __init__(self, poll_seconds=3.0, skip=False, parent=None):
        super().__init__(parent)
        self.poll_seconds = poll_seconds
        self._stop = False
        self._fails = 0
        if skip:
            self.mode, self.name, self.total, self.handle = (None, "", 0, None)
        else:
            self.mode, self.name, self.total, self.handle = self._init()

    def available(self):
        return self.mode is not None

    def _init(self):
        if pynvml is not None:
            try:
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                raw = pynvml.nvmlDeviceGetName(handle)
                name = raw.decode(errors="ignore") if isinstance(raw, bytes) else str(raw)
                return ("nvml", name.strip(), 0, handle)
            except Exception:
                pass
        if sys.platform == "win32":
            reg = _registry_gpu()
            if reg:
                return ("win", reg[0], reg[1], None)
        # linux gpu (sysfs/devfreq) not wired up yet
        return (None, "", 0, None)

    def run(self):
        if self.mode is None:
            return
        while not self._stop:
            info = self._poll()
            if info is not None:
                self._fails = 0
                self.gpu_ready.emit(info)
            else:
                self._fails += 1
                if self._fails == 4:  # one "no data" notice, then keep trying quietly
                    self.gpu_ready.emit(None)
            if self._stop:
                break
            self.msleep(int(self.poll_seconds * 1000))

    def _poll(self):
        if self.mode == "nvml":
            try:
                util = float(pynvml.nvmlDeviceGetUtilizationRates(self.handle).gpu)
                mem = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
                try:
                    temp = float(pynvml.nvmlDeviceGetTemperature(self.handle, pynvml.NVML_TEMPERATURE_GPU))
                except Exception:
                    temp = None
                return GpuInfo(self.name, util, mem.used, mem.total, temp)
            except Exception:
                return None
        if self.mode == "win":
            counters = _windows_gpu_counters(should_stop=lambda: self._stop)
            if counters is None:
                return None
            util, mem_used = counters
            # engines double-report a bit, cap it
            return GpuInfo(self.name, min(100.0, util), int(mem_used), self.total, None)
        return None

    def stop(self):
        self._stop = True
        # the powershell query is killable now, so this returns fast;
        # terminate is only a last resort
        if not self.wait(2000):
            self.terminate()
            self.wait(500)
