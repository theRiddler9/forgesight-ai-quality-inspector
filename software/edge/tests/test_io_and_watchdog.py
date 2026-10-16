import threading

from software.common.schemas import AlertType, InspectionDecision as R
from software.edge.io_control.debounce import Debouncer
from software.edge.io_control.gpio import MockGPIOController
from software.edge.watchdog.monitor import Watchdog


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_gpio_signal_matches_decision():
    g = MockGPIOController()
    s = g.show_result(R.PASS)
    assert (s.green, s.red, s.amber, s.buzzer) == (True, False, False, False)
    s = g.show_result(R.FAIL)
    assert (s.green, s.red, s.amber, s.buzzer) == (False, True, False, True)
    s = g.show_result(R.RECHECK)
    assert (s.green, s.red, s.amber, s.buzzer) == (False, False, True, False)
    s = g.show_fault()
    assert (s.green, s.red, s.amber, s.buzzer) == (False, False, True, True)


def test_ring_brightness_is_clamped_and_persists():
    g = MockGPIOController()
    g.set_ring_brightness(150)
    assert g.state.ring_pwm_pct == 100.0
    g.set_ring_brightness(40)
    g.show_result(R.PASS)
    assert g.state.ring_pwm_pct == 40.0
    g.close()
    assert not any([g.state.green, g.state.red, g.state.amber, g.state.buzzer])


def test_debounce_ignores_chatter_then_accepts():
    clk = FakeClock()
    d = Debouncer(window_ms=15, clock=clk)
    assert d.accept()
    clk.t = 0.005
    assert not d.accept()
    clk.t = 0.010
    assert not d.accept()
    clk.t = 0.020
    assert d.accept()


def test_watchdog_flags_stall_once():
    clk = FakeClock()
    wd = Watchdog(clock=clk)
    wd.begin_inspection()
    clk.t = 0.150
    assert wd.check() == []
    clk.t = 0.250
    (alert,) = wd.check()
    assert alert.alert_type == AlertType.PIPELINE_STALL and alert.value > 200
    assert wd.check() == []  # reported once per stall


def test_watchdog_no_stall_after_inspection_ends():
    clk = FakeClock()
    wd = Watchdog(clock=clk)
    wd.begin_inspection()
    wd.end_inspection()
    clk.t = 5.0
    assert wd.check() == []


def test_watchdog_camera_loss_after_three_missed_frames_and_recovery():
    wd = Watchdog()
    seen = []
    wd.subscribe(seen.append)
    wd.report_frame(False)
    wd.report_frame(False)
    assert not seen
    wd.report_frame(False)
    assert [a.alert_type for a in seen] == [AlertType.CAMERA_DISCONNECTED]
    wd.report_frame(False)
    assert len(seen) == 1  # not repeated
    wd.report_frame(True)
    for _ in range(3):
        wd.report_frame(False)
    assert len(seen) == 2  # re-arms after recovery


def test_watchdog_thermal_warning_has_hysteresis_reset():
    wd = Watchdog()
    wd.report_temperature(65.1)
    wd.report_temperature(64.9)  # brief dip below warning threshold does not rearm
    wd.report_temperature(66.0)
    assert len(wd.alerts) == 1 and wd.alerts[0].alert_type == AlertType.OVERHEATING
    wd.report_temperature(62.9)  # recovery threshold is 63 C by default
    wd.report_temperature(66.0)
    assert len(wd.alerts) == 2


def test_watchdog_isolates_subscriber_failures(caplog):
    wd = Watchdog()
    received = []

    def broken_subscriber(_alert):
        raise RuntimeError("subscriber failed")

    wd.subscribe(broken_subscriber)
    wd.subscribe(received.append)
    wd.report_temperature(66.0)

    assert len(received) == 1
    assert "watchdog alert subscriber failed" in caplog.text


def test_watchdog_can_stop_from_its_own_alert_callback():
    wd = Watchdog(stall_timeout_ms=1.0)
    callback_finished = threading.Event()

    def stop_from_callback(_alert):
        wd.stop()
        callback_finished.set()

    wd.subscribe(stop_from_callback)
    wd.begin_inspection()
    wd.start(poll_ms=1.0)

    assert callback_finished.wait(1.0)
    wd.stop()
    assert wd._thread is not None and not wd._thread.is_alive()
