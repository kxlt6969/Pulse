# changelog

## 0.6.3

- release-polish pass: refreshed screenshots for both themes, readme notes
  match how collection actually works now, `--interval` help text updated
  to the real 0.5s floor

## 0.6.2

- stability pass. the saved refresh interval was 0.2s, so the dashboard
  updated 5x a second and the gauge needles (500ms ease) were animating
  constantly and never settled — that's the jittery, bugged-out look.
  three fixes: saved interval reset to the 1s default, slider floor raised
  from 0.25s to 0.5s, and the needle ease duration now scales with the
  refresh interval (min 100ms) so it always settles between ticks

## 0.6.1

- fix the startup spike: the first cpu sample was taken immediately after
  priming the counters, so it measured over the app's own startup burst
  plus the first process scan — a ~0.3s window of self-inflicted load that
  read as 60-90% before settling. the first scan now runs before the
  counters are primed, and the first sample waits out one full interval,
  so the first numbers on screen are measured over a clean window
- cpu_freq (a wmi trip on windows) and disk partitions/usage are polled on
  a 3s/5s cadence with cached values between, like swap already was —
  per-tick psutil work is down to ~1% of a core at the 1s interval
- `--json` runs a throwaway process scan before measuring so per-process
  cpu% isn't 0 on the first pass

## 0.6.0

- visual pass: back to the deep navy + cyan/violet/green palette. cards get
  a subtle vertical gradient now, gauges have a soft glow under the arc,
  and the logo is the cyan-indigo gradient again
- disk chart: axis labels draw over the series instead of under it (spiky
  data buried them), and the top speed label no longer paints outside the
  widget edge
- disk card header fits now — title + two chips overflowed the narrow card,
  so it lost its "last 60 seconds" subtitle
- screenshots in docs/ re-captured for both themes

## 0.5.0

- the real lag culprit, found and fixed: two psutil calls were quietly
  eating the machine every tick. swap_memory() costs ~180ms per call on
  windows (it hits GetPerformanceInfo) and the process scan ~400ms on a
  busy box — together most of a second of gil-held work per tick, which
  the ui thread felt as stutter. swap is now polled every 15s and
  interpolated in between; the process scan self-tunes its cadence (spends
  ~10% of its time scanning, min 2s / max 15s) instead of running flat out
  every tick. steady-state per-tick cost on this machine went from ~600ms
  to well under 1ms
- dark mode is the default now, and the theme setting is stored correctly
  (it used to save the opposite of what you picked)
- when the window is hidden in the tray, per-tick ui work is skipped
  entirely — the numbers still collect and log, the widgets just sleep

## 0.4.0

- lag fixes: snapshot frames are coalesced on the ui side (a slow ui drops
  frames instead of stacking repaints), the tray micro-graph pushes a new
  icon to the shell every 2s instead of every tick (setIcon is an ipc
  round-trip), disk i/o deltas moved off the ui thread into the collector,
  and settings writes are debounced instead of firing on every slider tick

- tray icon is a live micro-graph now: the last 8 cpu samples as tiny bars,
  readable at a glance without opening anything
- filter box speaks a mini-language: `cpu>50`, `mem>100mb`, `mem<2g`,
  plain text, and combos like `cpu>50 mem>100mb`
- ctrl+shift+c copies the visible process rows as csv
- `--log FILE` appends one slim json line per snapshot while the app runs
- watchlist and the alerts on/off toggle survive restarts
- about dialog in the tray menu
- memory: snapshots are frozen slotted dataclasses, process rows are plain
  4-tuples again (the per-process psutil info dicts nobody read are gone)
- alerts now respect the pause key, and the temp card gets data in the gui
  (it only ever worked in `--json` before — nobody had noticed)
- process actions (kill/priority/affinity) moved to monitor/actions.py with
  one confirmation + error path for all of them
- tests/smoke.py: 25 headless checks, `python tests/smoke.py`

## 0.3.0

- bugfix pass: lite mode wasn't updating the process table at all (the
  early-return sat above it), double-click → details was never wired up,
  the watchlist died on a theme switch, the disk chart lost its speed
  axis, and `_autoscale` could be read before it existed
- new look: warm graphite + brass palette instead of the blue defaults,
  flat brass logo, lowercase card titles, less emoji. screenshots in
  docs/ refreshed in both themes
- main.py: interval/top/theme now persist between runs (slider changes are
  saved too); flags override saved values, everything is clamped to sane
  ranges; `--json` respects `--top`
- process detail popup: double-click a row (or right-click → Details) for
  command line, exe path, user, threads, priority, affinity + a live cpu
  sparkline. polls just that one process, once a second
- context menu on process rows: end task, end process tree, set priority
  (windows classes), set cpu affinity
- watchlist: right-click → Watch pins a process to the top of the table
- cpu/ram alerts: tray notification when something stays above the
  threshold for N seconds, names the top process. thresholds in settings
- freeze: space pauses updates, tray menu has a toggle too. ctrl+f filter,
  delete = end task, esc = clear filter/selection
- interval slider in the status bar, 0.25s–10s live
- disk activity chart (read/write bytes per second) + temp card where the
  kernel reports temps (linux mostly, windows needs drivers)
- `--json` prints one snapshot and exits, for scripts. `--no-gpu` skips
  gpu detection entirely
- settings persist between runs (QSettings): chart scale, window geometry
- ram card shows cached memory separately from used

## 0.2.3

- new `--lite` mode: no charts or overlay, lowest possible footprint
- gauges/core bars/overlay skip repaints when the numbers didn't change
- charts cap their redraw rate at 4/s (they redrew every tick before)
- dropped pyqtgraph (and numpy with it). the two charts are ~100 lines of
  QPainter now, same look. roughly half the RAM and a faster startup
- battery is polled every 15s instead of every tick
- table no longer flickers: rows update in place instead of being rebuilt
  every tick
- quitting is fast now. the gpu powershell query was unkillable and could
  hold up shutdown for ~15s; it gets killed on stop instead
- a dead network drive can't stall the poll loop anymore (slow mounts get
  benched for 60s)
- assorted repaint skips (disk gauge, tray tooltip, gpu name)

## 0.2.2

- cleanup pass, no feature changes (dead imports, comment tidy-up)
- is_dark() used a name that only existed at runtime, made it a real flag

## 0.2.1

- fix stylesheet colors getting mangled (`#101826_BORDER` warnings in the console)
- taskbar now says Pulse instead of python (explicit AppUserModelID)
- gpu polling moved to its own thread, it was stalling the 1s stat loop
- first paint is faster, dropped a redundant process scan at startup
- `--version` flag

## 0.2.0

- gpu card: nvidia via nvml, amd/intel on windows via the gpu perf counters
- filter box for the process table
- system tray mode + draggable mini overlay
- light theme

## 0.1.0

- first version: cpu/memory/disk/network gauges, rolling charts, process table
