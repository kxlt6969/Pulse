import pyqtgraph as pg
from PySide6.QtGui import QColor

from . import theme
from .fmt import human_bytes

pg.setConfigOptions(antialias=True, background=None, foreground=QColor(theme.MUTED))


class _SecondsAxis(pg.AxisItem):
    # x is "seconds ago", 0 = right edge
    def tickStrings(self, values, scale, spacing):
        labels = []
        for value in values:
            secs = int(round(value))
            labels.append("now" if secs >= 0 else f"{-secs}s")
        return labels


class _SpeedAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [f"{human_bytes(max(0.0, v))}/s" for v in values]


class LiveChart(pg.PlotWidget):
    """Rolling time-series chart over a fixed window of the last N samples."""

    def __init__(self, max_points=60, left_axis="hidden", parent=None):
        super().__init__(parent, background=None)
        self._max_points = max_points
        self._curves = {}

        plot = self.getPlotItem()
        plot.setMenuEnabled(False)
        plot.setMouseEnabled(x=False, y=False)
        plot.hideButtons()
        plot.showGrid(x=False, y=False)
        plot.setContentsMargins(4, 2, 4, 6)
        # fixed window so the graph scrolls like task manager's
        plot.setXRange(-(max_points - 1), 0, padding=0)

        axes = {"bottom": _SecondsAxis(orientation="bottom")}
        if left_axis == "speed":
            axes["left"] = _SpeedAxis(orientation="left")
        else:
            plot.getAxis("left").setVisible(False)

        for axis in axes.values():
            axis.setStyle(tickTextOffset=8)
            axis.setTextPen(QColor(theme.FAINT))
        plot.setAxisItems(axes)

    def add_series(self, name, color, fill=True):
        pen = pg.mkPen(color=QColor(color), width=2)
        options = {"pen": pen, "antialias": True}
        if fill:
            fill_color = QColor(color)
            fill_color.setAlpha(65)
            options.update({"brush": pg.mkBrush(fill_color), "fillLevel": 0})
        self._curves[name] = self.getPlotItem().plot(**options)

    def push(self, name, values):
        curve = self._curves.get(name)
        if curve is None:
            return
        ys = list(values)[-self._max_points:]
        xs = list(range(-len(ys) + 1, 1))
        curve.setData(xs, ys)

    def set_ylim(self, low, high):
        self.getPlotItem().setYRange(low, high, padding=0.06)
