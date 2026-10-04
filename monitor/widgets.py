from collections import deque
from math import sin

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


def _mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
    )


class LogoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._wobble = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.valueChanged.connect(self._on_tick)

    def _on_tick(self, value):
        self._wobble = float(value)
        self.update()

    def mousePressEvent(self, event):
        # poke the logo, it wiggles. took two minutes, worth it.
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = rect.width() * 0.28

        shape = QPainterPath()
        shape.addRoundedRect(rect, radius, radius)
        # cyan into indigo, corner to corner
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor("#22D3EE"))
        gradient.setColorAt(1.0, QColor("#6366F1"))
        painter.fillPath(shape, QBrush(gradient))

        if self._wobble > 0.0:
            painter.save()
            angle = sin(self._wobble * 3.14159) * -4.0
            center = rect.center()
            painter.translate(center)
            painter.rotate(angle)
            painter.translate(-center)

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

        if self._wobble > 0.0:
            painter.restore()


class GaugeWidget(QWidget):
    """270-degree arc gauge. Value changes are eased so it sweeps instead of jumping."""

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = color  # theme key name, resolved at paint time
        self._value = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._on_tick)
        self.set_rate(1.0)
        self.setFixedHeight(150)
        self.setMinimumWidth(150)

    def set_rate(self, interval):
        # ease duration must fit inside the refresh interval or the needle
        # never settles between ticks and just looks drunk
        self._animation.setDuration(int(max(100, min(500, interval * 400))))

    def set_value(self, value):
        value = max(0.0, min(100.0, float(value)))
        if abs(value - self._value) < 0.5:
            return  # same number as last tick, don't restart the animation
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

        track = QPen(QColor(theme.TRACK), pen_width)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        # angles are 1/16th degree, negative span = clockwise, 225° = bottom-left
        painter.drawArc(rect, 225 * 16, -270 * 16)

        if self._value > 0.15:
            accent = QColor(getattr(theme, self._color))
            # wide faint pass under the real arc, reads as a soft glow
            glow = QPen(accent, pen_width * 2.2)
            glow.setCapStyle(Qt.PenCapStyle.RoundCap)
            glow_color = QColor(accent)
            glow_color.setAlpha(28)
            glow.setColor(glow_color)
            painter.setPen(glow)
            span = int(-270 * 16 * (self._value / 100.0))
            painter.drawArc(rect, 225 * 16, span)

            arc = QPen(accent, pen_width)
            arc.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc)
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
        painter.setPen(QColor(theme.TITLE_TEXT))
        painter.drawText(QPointF(x, baseline), number)
        painter.setFont(pct_font)
        painter.setPen(QColor(theme.MUTED))
        painter.drawText(QPointF(x + num_width + 2, baseline - diameter * 0.05), "%")


class CoreBars(QWidget):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = color  # theme key name
        self._values = []
        self.setFixedHeight(34)

    def set_values(self, values):
        vals = [max(0.0, min(100.0, float(v))) for v in values]
        # average pairs if someone shows up with a 64-core threadripper
        while len(vals) > 32 and len(vals) >= 2:
            vals = [(vals[i] + vals[i + 1]) / 2.0 for i in range(0, len(vals) - 1, 2)]
        if vals == self._values:
            return
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
        track = QColor(theme.CORE_TRACK)
        base = QColor(theme.CORE_BASE)
        accent = QColor(getattr(theme, self._color))

        for i, value in enumerate(self._values):
            x = i * (bar_w + gap)
            radius = min(bar_w / 2.0, full_h / 2.0)
            painter.setBrush(track)
            painter.drawRoundedRect(QRectF(x, 1.0, bar_w, full_h), radius, radius)
            fill_h = max(3.0, full_h * value / 100.0)
            fill_radius = min(bar_w / 2.0, fill_h / 2.0)
            painter.setBrush(_mix(base, accent, value / 100.0))
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


class TemperatureCard(QWidget):
    # best-effort temp card. lives or dies with what the kernel reports.
    def __init__(self, parent=None):
        super().__init__(parent)
        row = QVBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(1)
        self.head = QLabel("temp")
        self.head.setStyleSheet(
            f"color: {theme.GPU}; font-size: 11px; font-weight: 700; background: transparent;"
        )
        self.value = QLabel("—")
        self.value.setObjectName("netValue")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.head)
        row.addWidget(self.value)
        self._last = None

    def set_temps(self, readings):
        # psutil shape: (label, current, high, critical), high/critical may be None
        if not readings:
            if self._last != ("n/a", ""):
                self._last = ("n/a", "")
                self.value.setText("n/a")
            return
        label, current, high, critical = readings[0]
        color = ""
        limit = critical or high
        if limit and current >= limit - 5.0:
            color = theme.DANGER
        elif high and current >= high - 10.0:
            color = theme.WARN
        text = f"{current:.0f}°C"
        if self._last == (text, color):
            return
        self._last = (text, color)
        self.head.setText(label[:14])
        if color:
            self.value.setStyleSheet(f"color: {color};")
        else:
            self.value.setStyleSheet("")
        self.value.setText(text)


class Sparkline(QWidget):
    """Tiny inline chart for the detail popup. ~1 minute of history."""

    def __init__(self, color_key="CPU", parent=None):
        super().__init__(parent)
        self._color_key = color_key
        self._values = deque(maxlen=60)
        self.setFixedHeight(46)

    def push(self, value):
        self._values.append(max(0.0, min(100.0, float(value))))
        self.update()

    def paintEvent(self, event):
        if len(self._values) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(getattr(theme, self._color_key))
        w = self.width() - 2.0
        h = self.height() - 2.0
        n = len(self._values)
        path = QPainterPath()
        for i, value in enumerate(self._values):
            x = 1.0 + w * i / (n - 1)
            y = 1.0 + h * (1.0 - value / 100.0)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.setPen(QPen(color, 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


class MiniOverlay(QWidget):
    """Always-on-top strip with cpu/ram/net. Drag to move, ✕ to close,
    double-click to bring the main window back."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(250, 132)
        self.on_close = None
        self.on_open = None
        self._drag_offset = None
        self._cpu = 0.0
        self._ram = 0.0
        self._net = ""
        self._close_rect = QRectF(self.width() - 30.0, 6.0, 24.0, 20.0)

    def set_data(self, cpu, ram, net_text):
        if cpu == self._cpu and ram == self._ram and net_text == self._net:
            return
        self._cpu = cpu
        self._ram = ram
        self._net = net_text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        card = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(theme.CARD_BORDER), 1))
        painter.setBrush(QColor(theme.CARD))
        painter.drawRoundedRect(card, 14, 14)

        label_font = QFont(self.font())
        label_font.setPointSizeF(8)
        label_font.setBold(True)
        value_font = QFont(self.font())
        value_font.setPointSizeF(9)
        value_font.setBold(True)
        small_font = QFont(self.font())
        small_font.setPointSizeF(7.5)

        w = self.width()

        painter.setPen(QColor(theme.FAINT))
        painter.setFont(label_font)
        painter.drawText(QPointF(14, 20), "pulse")
        painter.drawText(QRectF(self._close_rect), Qt.AlignmentFlag.AlignCenter, "✕")

        # cpu row
        painter.setPen(QColor(theme.MUTED))
        painter.setFont(label_font)
        painter.drawText(QPointF(14, 46), "CPU")
        painter.setPen(QColor(theme.TITLE_TEXT))
        painter.setFont(value_font)
        painter.drawText(QPointF(w - 44, 46), f"{self._cpu:.0f}%")
        self._bar(painter, 14, 52, w - 28, 5, self._cpu, theme.CPU)

        # ram row
        painter.setPen(QColor(theme.MUTED))
        painter.setFont(label_font)
        painter.drawText(QPointF(14, 78), "RAM")
        painter.setPen(QColor(theme.TITLE_TEXT))
        painter.setFont(value_font)
        painter.drawText(QPointF(w - 44, 78), f"{self._ram:.0f}%")
        self._bar(painter, 14, 84, w - 28, 5, self._ram, theme.RAM)

        painter.setPen(QColor(theme.MUTED))
        painter.setFont(small_font)
        painter.drawText(QPointF(14, 114), self._net)

    def _bar(self, painter, x, y, w, h, value, color_key):
        track = QRectF(x, y, w, h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.TRACK))
        painter.drawRoundedRect(track, h / 2.0, h / 2.0)
        fill_w = max(3.0, w * max(0.0, min(100.0, value)) / 100.0)
        painter.setBrush(QColor(getattr(theme, color_key)))
        painter.drawRoundedRect(QRectF(x, y, fill_w, h), h / 2.0, h / 2.0)

    def mousePressEvent(self, event):
        pos = event.position()
        if self._close_rect.contains(pos):
            self.hide()
            if self.on_close:
                self.on_close()
            return
        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def mouseDoubleClickEvent(self, event):
        if self.on_open:
            self.on_open()
