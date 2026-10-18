"""Kiểm thử tự động logic Smart Room (Bảng chân lý, Hysteresis, RPC, Timeout).

Chạy kiểm thử:
    python -m unittest tests/test_logic.py
    hoặc: python -m unittest discover tests
"""
from __future__ import annotations

import sys
import time
import unittest
from unittest.mock import MagicMock

# Cho phép chạy test trên môi trường chưa cài paho-mqtt
if "paho" not in sys.modules:
    sys.modules["paho"] = MagicMock()
    sys.modules["paho.mqtt"] = MagicMock()
    sys.modules["paho.mqtt.client"] = MagicMock()

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from logic import AutoController, RoomState, parse_bool


class FakeActuator:
    """Mock Actuator mô phỏng Switch để kiểm tra logic AutoController."""

    def __init__(self, auto_mode: bool = True) -> None:
        self.state = False
        self.auto_mode = auto_mode

    def set_state(self, state: bool, source: str = "") -> bool:
        changed = state != self.state
        self.state = state
        return changed


def make(auto_mode=True, threshold=30.0, timeout=10.0, hysteresis=1.0):
    room = RoomState(temperature_threshold=threshold, absence_timeout=timeout)
    light = FakeActuator(auto_mode)
    fan = FakeActuator(auto_mode)
    controller = AutoController(room, light, fan, hysteresis=hysteresis)
    return room, light, fan, controller


class AutoTruthTable(unittest.TestCase):
    """Bảng chân lý thiết kế: (Có người? x Nhiệt độ > Ngưỡng? -> Quạt, Đèn)."""

    def check(self, person: bool, temp: float, want_fan: bool, want_light: bool) -> None:
        room, light, fan, ctl = make()
        room.update_temperature(temp)
        room.update_person(person)
        ctl.evaluate()
        self.assertEqual((fan.state, light.state), (want_fan, want_light))

    def test_no_person_cool(self):
        self.check(False, 28, False, False)

    def test_no_person_hot(self):
        self.check(False, 32, False, False)

    def test_person_cool(self):
        self.check(True, 28, False, True)

    def test_person_hot(self):
        self.check(True, 32, True, True)


class AutoBehaviour(unittest.TestCase):
    """Kiểm tra hành vi trễ thời gian (absenceTimeout) và độ trễ nhiệt (hysteresis)."""

    def test_absence_timeout_keeps_light_then_turns_off(self):
        room, light, fan, ctl = make(timeout=0.3)
        room.update_temperature(35)
        room.update_person(True)
        ctl.evaluate()
        self.assertTrue(light.state and fan.state)

        room.update_person(False)  # Vừa mất dấu: chưa quá 0.3s timeout
        ctl.evaluate()
        self.assertTrue(light.state)

        time.sleep(0.4)  # Quá 0.3s timeout -> phải tắt
        ctl.evaluate()
        self.assertFalse(light.state or fan.state)

    def test_fan_hysteresis(self):
        room, light, fan, ctl = make(threshold=30, hysteresis=1.0)
        room.update_person(True)

        # > 30 -> bật
        room.update_temperature(31)
        ctl.evaluate()
        self.assertTrue(fan.state)

        # 29.5: vùng đệm (30 - 1.0 = 29.0) -> quạt vẫn giữ ON
        room.update_temperature(29.5)
        ctl.evaluate()
        self.assertTrue(fan.state)

        # <= 29.0 -> quạt tắt
        room.update_temperature(29.0)
        ctl.evaluate()
        self.assertFalse(fan.state)

    def test_manual_mode_does_nothing(self):
        room, light, fan, ctl = make(auto_mode=False)
        room.update_temperature(40)
        room.update_person(True)
        ctl.evaluate()
        self.assertFalse(light.state or fan.state)

    def test_missing_temperature_turns_fan_off(self):
        room, light, fan, ctl = make()
        room.update_person(True)
        ctl.evaluate()
        self.assertTrue(light.state)
        self.assertFalse(fan.state)


class RoomConfig(unittest.TestCase):
    """Kiểm tra RoomState nạp cấu hình và chuyển đổi tham số."""

    def test_apply_valid_config(self):
        room = RoomState()
        changed = room.apply_config({"temperatureThreshold": "28.5", "absenceTimeout": 5})
        self.assertEqual(room.temperature_threshold, 28.5)
        self.assertEqual(room.absence_timeout, 5)
        self.assertEqual(len(changed), 2)

    def test_invalid_values_are_ignored(self):
        room = RoomState()
        room.apply_config({"temperatureThreshold": "invalid_abc", "absenceTimeout": -1})
        self.assertEqual(room.temperature_threshold, 30.0)
        self.assertEqual(room.absence_timeout, 10.0)

    def test_parse_bool(self):
        self.assertTrue(parse_bool(True))
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("on"))
        self.assertTrue(parse_bool(1))
        self.assertTrue(parse_bool({"value": True}))
        self.assertTrue(parse_bool({"state": "true"}))
        self.assertTrue(parse_bool({"enabled": 1}))
        self.assertFalse(parse_bool(False))
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool(0))
        self.assertFalse(parse_bool("off"))
        self.assertFalse(parse_bool({"value": False}))


class IndependentAutoMode(unittest.TestCase):
    """Kiểm tra autoMode hoạt động độc lập giữa Đèn và Quạt."""

    def test_light_manual_fan_auto(self):
        room = RoomState()
        light = FakeActuator(auto_mode=False)
        fan = FakeActuator(auto_mode=True)
        ctl = AutoController(room, light, fan)

        room.update_person(True)
        room.update_temperature(35)
        ctl.evaluate()

        self.assertFalse(light.state)
        self.assertTrue(fan.state)

    def test_light_auto_fan_manual(self):
        room = RoomState()
        light = FakeActuator(auto_mode=True)
        fan = FakeActuator(auto_mode=False)
        ctl = AutoController(room, light, fan)

        room.update_person(True)
        room.update_temperature(35)
        ctl.evaluate()

        self.assertTrue(light.state)
        self.assertFalse(fan.state)


class FakeSwitch:
    """Mock Switch cho ActuatorRpcTest."""

    def __init__(self, name: str = "Fake") -> None:
        self.name = name
        self.is_on = False

    def set(self, on: bool) -> None:
        self.is_on = on

    def close(self) -> None:
        pass


class ActuatorRpcTest(unittest.TestCase):
    """Kiểm tra các lệnh RPC getState / setState / toggle trên ActuatorDevice."""

    def setUp(self):
        from thingsboard import ActuatorDevice

        cfg = type("Cfg", (), {"tb_tls": False})()
        self.switch = FakeSwitch("TestDevice")
        self.room = RoomState()
        self.device = ActuatorDevice("TestDevice", "dummy_token", cfg, self.switch, self.room, auto_mode=True)

    def test_get_state_rpc(self):
        self.switch.set(True)
        res = self.device.on_rpc("getState", None)
        self.assertTrue(res.get("state"))
        self.assertTrue(res.get("value"))
        self.assertTrue(res.get("autoMode"))

    def test_get_state_case_insensitive(self):
        self.switch.set(False)
        res = self.device.on_rpc("get_state", None)
        self.assertFalse(res.get("state"))

    def test_set_state_rejected_when_auto_mode_true(self):
        self.device.auto_mode = True
        self.switch.set(False)
        res = self.device.on_rpc("setState", True)
        self.assertTrue(self.device.auto_mode)
        self.assertFalse(self.device.state)
        self.assertFalse(res.get("success", False))
        self.assertIn("error", res)

        # After turning off autoMode, manual control succeeds
        self.device.auto_mode = False
        res2 = self.device.on_rpc("setState", True)
        self.assertTrue(self.device.state)
        self.assertTrue(res2.get("success", False))

    def test_set_state_with_dict_payload(self):
        self.device.auto_mode = False
        res = self.device.on_rpc("setValue", {"value": True})
        self.assertTrue(self.device.state)
        self.assertTrue(res.get("state"))

    def test_toggle_rpc(self):
        self.device.auto_mode = False
        self.switch.set(False)
        self.device.on_rpc("toggle", None)
        self.assertTrue(self.device.state)
        self.device.on_rpc("toggle", None)
        self.assertFalse(self.device.state)

    def test_shared_attributes_auto_mode_update(self):
        self.device.auto_mode = False
        self.device.on_attributes({"auto_mode": True})
        self.assertTrue(self.device.auto_mode)

        self.device.on_attributes({"autoMode": False})
        self.assertFalse(self.device.auto_mode)


if __name__ == "__main__":
    unittest.main()
