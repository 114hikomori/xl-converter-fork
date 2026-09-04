from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QCursor

from ui.widgets.slider import Slider


def _click(slider, x):
    """Simulate a left-click at pixel x within the slider, triggering click-to-position."""
    slider.mousePressEvent(QMouseEvent(
        QMouseEvent.MouseButtonPress, QPointF(x, 0), QCursor.pos(),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    ))


def test_setValueFromClick_zero_minimum_reaches_endpoints(app, qtbot):
    """Sanity check: a slider with minimum() == 0 maps click position linearly
    across [0, maximum]."""
    slider = Slider()
    qtbot.addWidget(slider)
    slider.setRange(0, 100)
    slider.resize(200, 24)

    _click(slider, 0)
    assert slider.value() == 0

    _click(slider, 200)
    assert slider.value() == 100


def test_setValueFromClick_nonzero_minimum_tick1_reaches_min_and_max(app, qtbot):
    """Regression test for the logged 'Slider click-to-position ignores a
    non-zero minimum' bug, using the exact minimum()=1 / tickInterval()=1
    configuration ui/tabs/output_tab.py's threads_sl actually ships with."""
    slider = Slider()
    qtbot.addWidget(slider)
    slider.setRange(1, 10)
    slider.setTickInterval(1)
    slider.resize(180, 24)

    _click(slider, 0)
    assert slider.value() == 1

    _click(slider, 180)
    assert slider.value() == 10


def test_setValueFromClick_zero_minimum_tick1_reaches_zero(app, qtbot):
    """A minimum()==0 slider whose tick interval resolves to 1 (Slider's own
    default when no tickInterval() is set) must be able to click all the way
    down to 0, not stop one unit above it."""
    slider = Slider()
    qtbot.addWidget(slider)
    slider.setRange(0, 100)
    # No explicit setTickInterval() call: _getTickInterval() defaults to 1.
    slider.resize(200, 24)

    _click(slider, 0)
    assert slider.value() == 0


def test_setValueFromClick_nonzero_minimum_tick_interval_offset(app, qtbot):
    """The tickInterval() > 1 snapping branch must also account for a
    non-zero minimum(), not just the tickInterval() == 1 branch."""
    slider = Slider()
    qtbot.addWidget(slider)
    slider.setRange(1, 100)
    slider.setTickInterval(5)
    slider.resize(99, 24)

    _click(slider, 47)
    assert slider.value() == 50
