import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme
from .fmt import human_bytes


class LiveChart(QWidget):
    """Rolling chart of the last N samples. Scrolling window, like task manager."""

    def __init__(self, max_points=60, left_axis="hidden", parent=None):
        super().__init__(parent)
        self._max_points = max_points
        self._series = {}  # name -> (color_key, values)
        self._ylim = (0.0, 100.0)
        self._fill = True
        self._speed_axis = left_axis == "speed"  # draw human_bytes/s ticks
        self._last_repaint = 0.0
        self.setMinimumHeight(150)

    def add_series(self, name, color_key, fill=True):
        self._series[name] = (color_key, [])
        self._fill = fill

    def push(self, name, values):
        entry = self._series.get(name)
        if entry is None:
            return
        # keep one spare point so the line still reaches "now" after trimming
        self._series[name] = (entry[0], list(values)[-self._max_points - 1:])
        now = time.monotonic()
        if now - self._last_repaint < 0.25:
            return  # faster redraws than this are invisible anyway
        self._last_repaint = now
        self.update()

    def set_ylim(self, low, high):
        self._ylim = (float(low), float(high))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        area = QRectF(self.rect()).adjusted(6.0, 6.0, -6.0, -6.0)
        if area.width() <= 10 or area.height() <= 10:
            return

        low, high = self._ylim
        span = (high - low) or 1.0

        for color_key, values in self._series.values():
            if not values:
                continue
            color = QColor(getattr(theme, color_key))
            points = self._to_points(values, area, low, span)
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)

            if self._fill:
                fill_color = QColor(color)
                fill_color.setAlpha(55)
                under = QPainterPath(path)
                under.lineTo(points[-1].x(), area.bottom())
                under.lineTo(points[0].x(), area.bottom())
                under.closeSubpath()
                painter.fillPath(under, fill_color)

            pen = QPen(color, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        # axis labels go on top of the series; spiky charts would bury them
        if self._is_speed_chart():
            self._draw_speed_axis(painter, area)
        self._draw_time_axis(painter, area)

    def _to_points(self, values, area, low, span):
        # x is spaced by sample slot and pinned to the right edge, so a
        # partially-filled chart grows in from "now" instead of from the left
        step = area.width() / (self._max_points - 1)
        points = []
        n = len(values)
        for i, value in enumerate(values):
            x = area.right() - step * (n - 1 - i)
            y = area.bottom() - (area.height() * (float(value) - low) / span)
            points.append(QPointF(x, y))
        return points

    def _is_speed_chart(self):
        return self._speed_axis

    def _draw_speed_axis(self, painter, area):
        low, high = self._ylim
        painter.setPen(QColor(theme.FAINT))
        font = painter.font()
        font.setPointSizeF(7.5)
        painter.setFont(font)
        for i in range(3):
            value = low + (high - low) * i / 2.0
            y = area.bottom() - area.height() * i / 2.0
            if i == 2:  # top label: the default position paints above the
                if area.height() < 150:  # widget edge; short charts just skip it
                    continue
                y = area.top() + 12.0
            painter.drawText(QPointF(6.0, y - 3.0), f"{human_bytes(max(0.0, value))}/s")

    def _draw_time_axis(self, painter, area):
        painter.setPen(QColor(theme.FAINT))
        font = painter.font()
        font.setPointSizeF(7.5)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        left = f"{-(self._max_points - 1)}s"
        painter.drawText(QPointF(area.left(), area.bottom() + 13.0), left)
        painter.drawText(QPointF(area.right() - metrics.horizontalAdvance("now"), area.bottom() + 13.0), "now")
