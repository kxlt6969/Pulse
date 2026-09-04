# Pulse

A desktop system monitor written in Python (PySide6 + psutil + pyqtgraph).

I wanted a Task Manager that doesn't hurt to look at, so I built my own.
Everything is drawn in code — the gauges, charts and logo are all QPainter
and pyqtgraph, no image assets anywhere. Works on Windows, Linux and macOS.

![screenshot](docs/screenshot.png)

## Running it

Python 3.10 or newer:

    pip install -r requirements.txt
    python main.py

A few flags:

| flag | what it does |
| --- | --- |
| `--interval 2` | refresh rate in seconds (default 1) |
| `--top 40` | how many processes to list (default 25) |
| `--screenshot out.png --wait 65` | run for N seconds, save a PNG of the window and quit — that's how I made the screenshot above |

## How it's put together

    main.py                entry point, CLI args
    monitor/app.py         main window, wires snapshots into the widgets
    monitor/collectors.py  QThread that polls psutil and emits snapshots
    monitor/widgets.py     custom-painted gauges, core bars, logo
    monitor/charts.py      pyqtgraph setup, rolling 60s charts
    monitor/processes.py   the sortable process table
    monitor/theme.py       colors + stylesheet, all in one place
    monitor/fmt.py         byte/duration formatting helpers

The process scan is the slowest psutil call by far, so the whole poll loop
lives on a worker thread and the UI thread only ever touches already-collected
data. That's why the gauges keep animating smoothly while the table refreshes.

## Notes

- Per-process CPU% is divided by core count so 100% = all cores, the same
  convention Task Manager uses. htop people: divide by nothing in
  `collectors.py` if you prefer it raw.
- psutil needs two samples for CPU%, so the first tick reads 0 — the worker
  primes the counters on startup to skip the dead second.
- Network totals are since boot, because that's what the kernel counters give you.

## TODO

- GPU usage / temps (annoying to do cross-platform)
- filter box for the process table
- tray mode with a mini overlay
- light theme

MIT — see [LICENSE](LICENSE).
