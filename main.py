import argparse
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from monitor import __version__, theme
from monitor.app import MainWindow
from monitor.widgets import LogoWidget


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="pulse", description="Pulse — system monitor")
    parser.add_argument("--interval", type=float, default=1.0, help="refresh interval in seconds (default: 1.0)")
    parser.add_argument("--top", type=int, default=25, help="number of processes to show (default: 25)")
    parser.add_argument("--screenshot", metavar="PATH", help="render for --wait seconds, save a PNG of the window and exit")
    parser.add_argument("--wait", type=float, default=6.0, help="seconds to run before --screenshot fires (default: 6)")
    return parser.parse_args(argv)


def _apply_dark_titlebar(window):
    # windows 10/11 only, harmless anywhere else
    if sys.platform != "win32":
        return
    import ctypes

    try:
        hwnd = int(window.winId())
        value = ctypes.c_int(1)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE, new value first
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), 4) == 0:
                break
    except Exception:
        pass


def main(argv=None):
    args = parse_args(argv)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLESHEET)

    font = QFont()
    font.setFamilies(["Segoe UI Variable Display", "Segoe UI", "Inter", "Noto Sans", "Ubuntu"])
    font.setPointSizeF(10)
    app.setFont(font)

    logo = LogoWidget()
    logo.resize(256, 256)
    app.setWindowIcon(QIcon(logo.grab()))

    window = MainWindow(interval=args.interval, top=args.top)
    window.show()
    _apply_dark_titlebar(window)

    if args.screenshot:

        def capture():
            path = os.path.abspath(args.screenshot)
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            window.grab().save(path)
            window.close()
            app.quit()

        QTimer.singleShot(int(max(1.0, args.wait) * 1000), capture)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
