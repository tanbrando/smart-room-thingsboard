"""Core logic: Thread-safe RoomState memory & periodic AutoController."""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

log = logging.getLogger("ctrl")

ATTR_TEMPERATURE = "temperatureThreshold"
ATTR_ABSENCE = "absenceTimeout"
ATTR_AUTO_MODE = "autoMode"


def parse_bool(value: Any) -> bool:
    """Convert input to boolean, supporting boolean strings and dict payloads."""
    if isinstance(value, dict):
        value = value.get("value", value.get("state", value.get("enabled", False)))
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes")
    return bool(value)


def _to_number(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


# =========================================================================== #
class RoomState:
    """Thread-safe state store shared across hardware devices and controllers."""

    def __init__(self, temperature_threshold: float = 30.0, absence_timeout: float = 10.0) -> None:
        self._lock = threading.RLock()
        self._threshold = float(temperature_threshold)
        self._absence_timeout = float(absence_timeout)
        self._temperature: float | None = None
        self._temperature_at = 0.0
        self._person = False
        self._last_seen: float | None = None

    @property
    def temperature_threshold(self) -> float:
        with self._lock:
            return self._threshold

    @property
    def absence_timeout(self) -> float:
        with self._lock:
            return self._absence_timeout

    def apply_config(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Updates Shared Attributes (temperatureThreshold, absenceTimeout)."""
        changed: dict[str, Any] = {}
        with self._lock:
            if ATTR_TEMPERATURE in attrs:
                val = _to_number(attrs[ATTR_TEMPERATURE])
                if val is not None and val != self._threshold:
                    self._threshold = changed[ATTR_TEMPERATURE] = val
                elif val is None:
                    log.warning("Invalid value for %s: %r", ATTR_TEMPERATURE, attrs[ATTR_TEMPERATURE])

            if ATTR_ABSENCE in attrs:
                val = _to_number(attrs[ATTR_ABSENCE])
                if val is not None and val >= 0 and val != self._absence_timeout:
                    self._absence_timeout = changed[ATTR_ABSENCE] = val
                elif val is None or val < 0:
                    log.warning("Invalid value for %s: %r", ATTR_ABSENCE, attrs[ATTR_ABSENCE])

        return changed

    def update_temperature(self, value: float) -> None:
        with self._lock:
            self._temperature = float(value)
            self._temperature_at = time.monotonic()

    def get_temperature(self, max_age: float | None = None) -> float | None:
        with self._lock:
            if self._temperature is None:
                return None
            if max_age is not None and (time.monotonic() - self._temperature_at) > max_age:
                return None
            return self._temperature

    def update_person(self, detected: bool) -> None:
        with self._lock:
            if detected or self._person:
                self._last_seen = time.monotonic()
            self._person = bool(detected)

    def is_occupied(self) -> bool:
        with self._lock:
            if self._person:
                return True
            if self._last_seen is None:
                return False
            return (time.monotonic() - self._last_seen) < self._absence_timeout


# =========================================================================== #
class AutoController:
    """Periodic automation loop: Light on if occupied, Fan on if occupied AND hot."""

    def __init__(
        self,
        room: RoomState,
        light: Any,
        fan: Any,
        hysteresis: float = 1.0,
        temperature_max_age: float = 60.0,
        interval: float = 1.0,
    ) -> None:
        self._room = room
        self._light = light
        self._fan = fan
        self._hysteresis = hysteresis
        self._max_age = temperature_max_age
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="auto-controller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 2.0)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.evaluate()
            except Exception:  # noqa: BLE001
                log.exception("Error in AUTO evaluation loop")

    def evaluate(self) -> None:
        occupied = self._room.is_occupied()

        # 1. Light control
        if getattr(self._light, "auto_mode", True):
            reason = "AUTO (Occupied)" if occupied else "AUTO (Vacant)"
            self._light.set_state(occupied, reason)

        # 2. Fan control
        if getattr(self._fan, "auto_mode", True):
            desired, reason = self._desired_fan(occupied)
            self._fan.set_state(desired, reason)

    def _desired_fan(self, occupied: bool) -> tuple[bool, str]:
        if not occupied:
            return False, "AUTO (Room vacant)"

        temp = self._room.get_temperature(self._max_age)
        if temp is None:
            return False, "AUTO (Temperature data stale/missing)"

        threshold = self._room.temperature_threshold
        if temp > threshold:
            return True, f"AUTO (Temperature {temp:.1f} C > {threshold:.1f} C)"

        off_threshold = threshold - self._hysteresis
        if temp <= off_threshold:
            return False, f"AUTO (Temperature {temp:.1f} C <= {off_threshold:.1f} C)"

        return self._fan.state, "AUTO (Hysteresis buffer)"

