import argparse
import json
import os
import sys
from dataclasses import asdict

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from monitor import __version__, theme
from monitor.app import MainWindow, apply_titlebar
from monitor.widgets import LogoWidget


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="pulse", description="Pulse — system monitor")
    parser.add_argument("--interval", type=float, default=None, help="refresh interval in seconds, 0.5-10 (default: last used)")
    parser.add_argument("--top", type=int, default=None, help="number of processes to show (default: last used)")
    parser.add_argument("--light", action="store_true", help="start in light theme")
    parser.add_argument("--lite", action="store_true", help="minimal mode: no charts or overlay, lowest memory")
    parser.add_argument("--json", action="store_true", help="print one snapshot as JSON and exit (no window)")
    parser.add_argument("--log", metavar="FILE", help="append every snapshot to FILE as JSON lines, while the app runs")
    parser.add_argument("--no-gpu", action="store_true", help="skip GPU detection entirely")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--screenshot", metavar="PATH", help="render for --wait seconds, save a PNG of the window and exit")
    parser.add_argument("--wait", type=float, default=6.0, help="seconds to run before --screenshot fires (default: 6)")
    return parser.parse_args(argv)


def _use_pulse_app_id():
    # without an explicit AppUserModelID windows groups the window under
    # "python" in the taskbar instead of the app name
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("kxlt6969.pulse")
    except Exception:
        pass


def main(argv=None):
    args = parse_args(argv)

    if args.json:
        # no window, no theme, no event loop — print one snapshot and get out
        from monitor.collectors import collect_snapshot

        snapshot = collect_snapshot(process_limit=args.top or 25)
        print(json.dumps(asdict(snapshot), default=str))
        return 0

    settings = QSettings("kxlt6969", "Pulse")

    # flags win over saved settings, saved settings win over defaults
    interval = args.interval
    if interval is None:
        interval = settings.value("run/interval", 1.0, type=float)
    # below 0.5s the gauge animation can't settle between ticks and the
    # whole dashboard reads as jittery; not a trade worth offering
    interval = max(0.5, min(10.0, float(interval)))

    top = args.top
    if top is None:
        top = settings.value("run/top", 25, type=int)
    top = max(5, min(200, int(top)))
    settings.setValue("run/top", top)

    if args.light:
        theme.use_light()
    elif settings.value("run/theme", "dark", type=str) == "light":
        theme.use_light()

    _use_pulse_app_id()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.stylesheet())

    font = QFont()
    font.setFamilies(["Segoe UI Variable Display", "Segoe UI", "Inter", "Noto Sans", "Ubuntu"])
    font.setPointSizeF(10)
    app.setFont(font)

    logo = LogoWidget()
    logo.resize(256, 256)
    app.setWindowIcon(QIcon(logo.grab()))

    window = MainWindow(
        interval=interval,
        top=top,
        lite=args.lite,
        gpu=not args.no_gpu,
        log_file=args.log,
    )
    window.show()
    apply_titlebar(window, dark=theme.is_dark())

    if args.screenshot:

        def capture():
            path = os.path.abspath(args.screenshot)
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            window.grab().save(path)
            window.force_exit()
            app.quit()

        QTimer.singleShot(int(max(1.0, args.wait) * 1000), capture)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
