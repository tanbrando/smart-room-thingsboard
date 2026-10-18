"""Raspberry Pi 4B hardware drivers (DHT11, LED, DCFan, CameraDetector)."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger("hw")


class SensorReadError(Exception):
    """Temporary sensor read failure (checksum/timing)."""


# =========================================================================== #
# Real Hardware Drivers (Raspberry Pi 4B)
# =========================================================================== #
class DHT11:
    def __init__(self, bcm_pin: int) -> None:
        import adafruit_dht
        import board

        # Tự động dọn dẹp tiến trình libgpiod_pulsein bị treo từ lần chạy trước
        if sys.platform.startswith("linux"):
            try:
                subprocess.run(["pkill", "-9", "-f", "libgpiod_pulsein"], capture_output=True)
                time.sleep(0.2)
            except Exception:
                pass

        try:
            pin = getattr(board, f"D{bcm_pin}")
        except AttributeError as exc:
            raise ValueError(f"Pin GPIO{bcm_pin} does not exist on board") from exc
        self._dht = adafruit_dht.DHT11(pin)

    def read(self) -> tuple[float, float]:
        """Returns tuple of (temperature °C, relative humidity %)."""
        try:
            t, h = self._dht.temperature, self._dht.humidity
        except Exception as exc:
            raise SensorReadError(str(exc)) from exc
        if t is None or h is None:
            raise SensorReadError("Sensor returned None")
        return float(t), float(h)

    def close(self) -> None:
        try:
            self._dht.exit()
        except Exception:  # noqa: BLE001
            pass
        if sys.platform.startswith("linux"):
            try:
                subprocess.run(["pkill", "-9", "-f", "libgpiod_pulsein"], capture_output=True)
            except Exception:
                pass


class Led:
    """LED connected to GPIO via current-limiting resistor or transistor driver."""

    def __init__(self, bcm_pin: int) -> None:
        import RPi.GPIO as GPIO

        self._gpio = GPIO
        self._pin = bcm_pin
        self._state = False

        self._gpio.setmode(self._gpio.BCM)
        self._gpio.setwarnings(False)
        self._gpio.setup(self._pin, self._gpio.OUT, initial=self._gpio.LOW)

    @property
    def is_on(self) -> bool:
        return self._state

    def set(self, state: bool) -> None:
        self._state = bool(state)
        self._gpio.output(self._pin, self._gpio.HIGH if self._state else self._gpio.LOW)

    def close(self) -> None:
        self.set(False)
        try:
            self._gpio.cleanup(self._pin)
        except Exception:  # noqa: BLE001
            pass


class DCFan:
    """DC Fan driven by H-Bridge (L298N) or 1-channel MOSFET switch."""

    def __init__(
        self,
        in1: int,
        in2: int | None = None,
        enable: int | None = None,
        speed: float = 1.0,
    ) -> None:
        import RPi.GPIO as GPIO

        self._gpio = GPIO
        self._in1 = in1
        self._in2 = in2
        self._enable = enable
        self._speed = max(0.0, min(1.0, speed))
        self._on = False
        self._pwm = None

        self._gpio.setmode(self._gpio.BCM)
        self._gpio.setwarnings(False)

        pins = [in1]
        if in2 is not None:
            pins.append(in2)
        if enable is not None:
            pins.append(enable)

        for p in pins:
            self._gpio.setup(p, self._gpio.OUT, initial=self._gpio.LOW)

        if enable is not None:
            self._pwm = self._gpio.PWM(enable, 1000)
            self._pwm.start(0)
        elif in2 is None:
            self._pwm = self._gpio.PWM(in1, 1000)
            self._pwm.start(0)

    @property
    def is_on(self) -> bool:
        return self._on

    def set(self, state: bool) -> None:
        self._on = bool(state)
        duty = (self._speed * 100.0) if self._on else 0.0

        if self._in2 is not None:
            if self._on:
                self._gpio.output(self._in1, self._gpio.HIGH)
                self._gpio.output(self._in2, self._gpio.LOW)
            else:
                self._gpio.output(self._in1, self._gpio.LOW)
                self._gpio.output(self._in2, self._gpio.LOW)

            if self._pwm is not None:
                self._pwm.ChangeDutyCycle(duty)
        else:
            if self._pwm is not None:
                self._pwm.ChangeDutyCycle(duty)
            else:
                self._gpio.output(self._in1, self._gpio.HIGH if self._on else self._gpio.LOW)

    def close(self) -> None:
        self.set(False)
        if self._pwm is not None:
            try:
                self._pwm.stop()
            except Exception:  # noqa: BLE001
                pass
        pins = [p for p in (self._in1, self._in2, self._enable) if p is not None]
        try:
            self._gpio.cleanup(pins)
        except Exception:  # noqa: BLE001
            pass


def _load_cascades(cv2_mod: Any, custom_path: str | None = None) -> list[tuple[str, Any]]:
    cascades: list[tuple[str, Any]] = []

    # 1. Custom path nếu người dùng cấu hình riêng
    if custom_path and os.path.isfile(custom_path):
        c = cv2_mod.CascadeClassifier(custom_path)
        if not c.empty():
            return [(os.path.basename(custom_path), c)]

    # 2. Lấy trực tiếp từ thư mục resources/ nội bộ của project
    rsc_dir = Path(__file__).resolve().parent / "resources"
    targets = [
        ("upperbody", "haarcascade_upperbody.xml"),
        ("face", "haarcascade_frontalface_default.xml"),
        ("fullbody", "haarcascade_fullbody.xml"),
    ]

    for tag, filename in targets:
        xml_path = rsc_dir / filename
        if xml_path.is_file():
            c = cv2_mod.CascadeClassifier(str(xml_path))
            if not c.empty():
                cascades.append((tag, c))

    return cascades


class CameraDetector:
    """CSI Camera (Picamera2) + Multi-cascade Haar for robust presence detection."""

    def __init__(
        self,
        cascade_path: str | None,
        resolution: tuple[int, int],
        scale_factor: float,
        min_neighbors: int,
        min_size: tuple[int, int],
        detect_interval: float,
        confirm_frames: int,
        hold_seconds: float,
        show_preview: bool = False,
    ) -> None:
        import cv2
        # pyrefly: ignore[missing-import]
        from picamera2 import Picamera2

        self._cv2 = cv2
        self._cascades = _load_cascades(cv2, cascade_path)
        if not self._cascades:
            raise FileNotFoundError("Cannot load any Haar cascade model. Ensure opencv-data is installed.")

        model_names = [name for name, _ in self._cascades]
        log.info("Loaded detection models: %s", ", ".join(model_names))

        self._scale, self._neighbors, self._min_size = scale_factor, min_neighbors, min_size
        self._interval, self._confirm, self._hold = detect_interval, max(1, confirm_frames), hold_seconds
        self._show_preview = bool(show_preview)
        self._window_name = "Smart Room - Edge AI Camera (VNC Debug)"
        self._preview_lock = threading.Lock()
        self._latest_preview: tuple[Any, Any, bool] | None = None

        self._camera = Picamera2()
        self._camera.configure(
            self._camera.create_video_configuration(main={"size": resolution, "format": "RGB888"})
        )

        self.person_detected = False
        self._on_change: Callable[[bool], None] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, on_change: Callable[[bool], None]) -> None:
        self._on_change = on_change
        self._camera.start()
        self._thread = threading.Thread(target=self._run, name="camera-detector", daemon=True)
        self._thread.start()

    def render_preview(self) -> bool:
        """Renders GUI window on the MAIN thread to avoid GTK/GLib multithreading conflicts."""
        if not self._show_preview:
            return False

        with self._preview_lock:
            data = self._latest_preview

        if data is None:
            try:
                self._cv2.waitKey(20)
            except Exception:  # noqa: BLE001
                pass
            return True

        frame, hits, detected = data
        try:
            display_frame = self._cv2.cvtColor(frame, self._cv2.COLOR_RGB2BGR)
            for (x, y, w, h) in hits:
                self._cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                self._cv2.putText(
                    display_frame, "Person", (x, max(18, y - 6)),
                    self._cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1
                )

            status_str = "PERSON DETECTED" if detected else "VACANT"
            status_color = (0, 255, 0) if detected else (0, 0, 255)
            self._cv2.putText(
                display_frame, f"State: {status_str}", (10, 25),
                self._cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2
            )

            self._cv2.imshow(self._window_name, display_frame)
            key = self._cv2.waitKey(20) & 0xFF
            if key in (ord("q"), 27):  # 'q' or ESC pressed
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not display camera preview window: %s", exc)
            self._show_preview = False
            return False

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        if self._show_preview:
            try:
                self._cv2.destroyAllWindows()
            except Exception:  # noqa: BLE001
                pass
        try:
            self._camera.stop()
            self._camera.close()
        except Exception:  # noqa: BLE001
            pass

    def _run(self) -> None:
        streak, last_positive = 0, 0.0
        while not self._stop.is_set():
            started = time.monotonic()
            hits = ()
            frame = None
            try:
                frame = self._camera.capture_array()
                # Correct color conversion: Picamera2 captured frame is RGB888
                gray = self._cv2.cvtColor(frame, self._cv2.COLOR_RGB2GRAY)
                all_hits = []
                for name, cascade in self._cascades:
                    min_s = (45, 45) if name in ("face", "upperbody") else self._min_size
                    found_boxes = cascade.detectMultiScale(
                        gray, scaleFactor=self._scale, minNeighbors=self._neighbors, minSize=min_s
                    )
                    if len(found_boxes) > 0:
                        all_hits.extend(found_boxes)
                        break  # Match found, skip remaining cascades to keep CPU usage low

                hits = tuple(all_hits)
                found = len(hits) > 0
            except Exception:  # noqa: BLE001
                log.exception("Error processing camera frame")
                self._stop.wait(1.0)
                continue

            now = time.monotonic()
            if found:
                streak, last_positive = streak + 1, now
            else:
                streak = 0

            if not self.person_detected and streak >= self._confirm:
                self._set(True)
            elif self.person_detected and (now - last_positive) >= self._hold:
                self._set(False)

            if self._show_preview and frame is not None:
                with self._preview_lock:
                    self._latest_preview = (frame, hits, self.person_detected)

            remaining = self._interval - (time.monotonic() - started)
            if remaining > 0:
                self._stop.wait(remaining)

    def _set(self, detected: bool) -> None:
        self.person_detected = detected
        log.debug("Camera detection status: %s", "DETECTED" if detected else "VACANT")
        if self._on_change:
            try:
                self._on_change(detected)
            except Exception:  # noqa: BLE001
                pass


# =========================================================================== #
# Hardware Factory
# =========================================================================== #
def create_hardware(cfg) -> dict[str, any]:
    return {
        "sensor": DHT11(cfg.dht_pin),
        "detector": CameraDetector(
            cfg.haar_path, cfg.camera_resolution, cfg.haar_scale, cfg.haar_neighbors,
            cfg.haar_min_size, cfg.detect_interval, cfg.confirm_frames, cfg.hold_seconds,
            show_preview=cfg.camera_preview,
        ),
        "fan": DCFan(cfg.fan_in1, cfg.fan_in2, cfg.fan_enable, cfg.fan_speed),
        "light": Led(cfg.led_pin),
    }

