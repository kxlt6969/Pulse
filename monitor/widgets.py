from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from . import theme


def _mix(first, second, t):
    t = max(0.0, min(1.0, t))
    return QColor(
        int(first.red() + (second.red() - first.red()) * t),
        int(first.green() + (second.green() - first.green()) * t),
        int(first.blue() + (second.blue() - first.blue()) * t),
    )


class LogoWidget(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = rect.width() * 0.28

        shape = QPainterPath()
        shape.addRoundedRect(rect, radius, radius)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor("#22D3EE"))
        gradient.setColorAt(1.0, QColor("#6366F1"))
        painter.fillPath(shape, QBrush(gradient))

        # little heartbeat line
        w, h = rect.width(), rect.height()
        points = [
            (0.14, 0.58), (0.32, 0.58), (0.40, 0.24), (0.50, 0.82),
            (0.585, 0.38), (0.65, 0.58), (0.86, 0.58),
        ]
        pulse = QPainterPath(QPointF(rect.left() + points[0][0] * w, rect.top() + points[0][1] * h))
        for px, py in points[1:]:
            pulse.lineTo(rect.left() + px * w, rect.top() + py * h)

        pen = QPen(QColor("#FFFFFF"), max(2.0, w * 0.055))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(pulse)


class GaugeWidget(QWidget):
    """270-degree arc gauge. Value changes are eased so it sweeps instead of jumping."""

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._value = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(500)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._on_tick)
        self.setFixedHeight(150)
        self.setMinimumWidth(150)

    def set_value(self, value):
        value = max(0.0, min(100.0, float(value)))
        self._animation.stop()
        self._animation.setStartValue(self._value)
        self._animation.setEndValue(value)
        self._animation.start()

    def _on_tick(self, value):
        self._value = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height())
        margin = 6.0
        diameter = side - 2.0 * margin
        rect = QRectF((self.width() - diameter) / 2.0, margin, diameter, diameter)
        pen_width = max(8.0, min(13.0, diameter * 0.085))

        track = QPen(QColor("#1B2740"), pen_width)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        # angles are 1/16th degree, negative span = clockwise, 225° = bottom-left
        painter.drawArc(rect, 225 * 16, -270 * 16)

        if self._value > 0.15:
            arc = QPen(self._color, pen_width)
            arc.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc)
            span = int(-270 * 16 * (self._value / 100.0))
            painter.drawArc(rect, 225 * 16, span)

        center = rect.center()
        number = str(int(round(self._value)))

        num_font = QFont(self.font())
        num_font.setPixelSize(max(10, int(diameter * 0.26)))
        num_font.setBold(True)
        num_width = QFontMetrics(num_font).horizontalAdvance(number)

        pct_font = QFont(self.font())
        pct_font.setPixelSize(max(8, int(diameter * 0.12)))
        pct_font.setBold(True)
        pct_width = QFontMetrics(pct_font).horizontalAdvance("%")

        x = center.x() - (num_width + pct_width + 2) / 2.0
        baseline = center.y() + num_font.pixelSize() * 0.35

        painter.setFont(num_font)
        painter.setPen(QColor("#F4F7FC"))
        painter.drawText(QPointF(x, baseline), number)
        painter.setFont(pct_font)
        painter.setPen(QColor(theme.MUTED))
        painter.drawText(QPointF(x + num_width + 2, baseline - diameter * 0.05), "%")


class CoreBars(QWidget):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._base = QColor("#2A3A55")
        self._values = []
        self.setFixedHeight(34)

    def set_values(self, values):
        vals = [max(0.0, min(100.0, float(v))) for v in values]
        # average pairs if someone shows up with a 64-core threadripper
        while len(vals) > 32 and len(vals) >= 2:
            vals = [(vals[i] + vals[i + 1]) / 2.0 for i in range(0, len(vals) - 1, 2)]
        self._values = vals
        self.update()

    def paintEvent(self, event):
        if not self._values:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        n = len(self._values)
        gap = 3.0
        bar_w = max(2.0, (self.width() - gap * (n - 1)) / n)
        full_h = self.height() - 2.0
        track = QColor("#141D2C")

        for i, value in enumerate(self._values):
            x = i * (bar_w + gap)
            radius = min(bar_w / 2.0, full_h / 2.0)
            painter.setBrush(track)
            painter.drawRoundedRect(QRectF(x, 1.0, bar_w, full_h), radius, radius)
            fill_h = max(3.0, full_h * value / 100.0)
            fill_radius = min(bar_w / 2.0, fill_h / 2.0)
            painter.setBrush(_mix(self._base, self._color, value / 100.0))
            painter.drawRoundedRect(QRectF(x, 1.0 + full_h - fill_h, bar_w, fill_h), fill_radius, fill_radius)


class NetStat(QWidget):
    def __init__(self, arrow, color, title, parent=None):
        super().__init__(parent)
        row = QVBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(1)

        head = QLabel(f"{arrow}  {title}")
        head.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 700; background: transparent;")
        self.value = QLabel("0 B/s")
        self.value.setObjectName("netValue")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        row.addWidget(head)
        row.addWidget(self.value)

    def set_value(self, text):
        self.value.setText(text)
