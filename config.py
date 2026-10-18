"""System configuration loaded from environment variables or local .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if " #" in line:
            line = line.split(" #", 1)[0].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _get(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    return default if val is None or val.strip() == "" else val.strip()


def _int(name: str, default: int) -> int:
    return int(_get(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(_get(name, str(default)))


def _bool(name: str, default: bool) -> bool:
    val = _get(name)
    return default if val is None else val.lower() in ("1", "true", "yes", "on")


def _opt_int(name: str) -> int | None:
    val = _get(name)
    return None if val is None else int(val)


def _pair(name: str, default: str) -> tuple[int, int]:
    val = str(_get(name, default))
    a, b = val.split(",")
    return int(a.strip()), int(b.strip())


@dataclass(frozen=True)
class Config:
    # --- ThingsBoard MQTT ---
    tb_host: str
    tb_port: int
    tb_tls: bool
    tb_keepalive: int
    token_environment: str
    token_presence: str
    token_fan: str
    token_light: str

    # --- Chân GPIO (BCM) ---
    dht_pin: int
    led_pin: int
    fan_in1: int
    fan_in2: int | None
    fan_enable: int | None
    fan_speed: float

    # --- Cảm biến & Camera CSI ---
    sample_interval: float
    camera_resolution: tuple[int, int]
    camera_preview: bool
    haar_path: str | None
    haar_scale: float
    haar_neighbors: int
    haar_min_size: tuple[int, int]
    detect_interval: float
    confirm_frames: int
    hold_seconds: float

    # --- Tham số & Ngưỡng mặc định ---
    default_auto_fan: bool
    default_auto_light: bool
    default_threshold: float
    default_absence: float
    fan_hysteresis: float
    temp_max_age: float
    control_interval: float

    # --- Khác ---
    log_level: str

    def validate(self) -> None:
        required = {
            "TB_TOKEN_ENVIRONMENT": self.token_environment,
            "TB_TOKEN_PRESENCE": self.token_presence,
            "TB_TOKEN_FAN": self.token_fan,
            "TB_TOKEN_LIGHT": self.token_light,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ConfigError("Missing required access token(s) in .env: " + ", ".join(missing))


def load_config(env_path: Path | None = None) -> Config:
    target = env_path if env_path is not None else ROOT / ".env"
    _load_dotenv(target)

    return Config(
        tb_host=_get("TB_HOST", "eu.thingsboard.cloud"),
        tb_port=_int("TB_PORT", 1883),
        tb_tls=_bool("TB_TLS", False),
        tb_keepalive=_int("TB_KEEPALIVE", 60),
        token_environment=_get("TB_TOKEN_ENVIRONMENT", ""),
        token_presence=_get("TB_TOKEN_PRESENCE", ""),
        token_fan=_get("TB_TOKEN_FAN", ""),
        token_light=_get("TB_TOKEN_LIGHT", ""),
        dht_pin=_int("DHT_PIN", 4),
        led_pin=_int("LED_PIN", 17),
        fan_in1=_int("FAN_PIN_IN1", 27),
        fan_in2=_opt_int("FAN_PIN_IN2"),
        fan_enable=_opt_int("FAN_PIN_ENABLE"),
        fan_speed=_float("FAN_SPEED", 1.0),
        sample_interval=max(2.0, _float("SAMPLE_INTERVAL", 5.0)),
        camera_resolution=_pair("CAMERA_RESOLUTION", "640,480"),
        camera_preview=_bool("CAMERA_PREVIEW", False) or _bool("CAMERA_SHOW_PREVIEW", False) or _bool("CAMERA_DEBUG", False),
        haar_path=_get("HAAR_CASCADE_PATH"),
        haar_scale=_float("HAAR_SCALE_FACTOR", 1.1),
        haar_neighbors=_int("HAAR_MIN_NEIGHBORS", 3),
        haar_min_size=_pair("HAAR_MIN_SIZE", "60,120"),
        detect_interval=_float("DETECT_INTERVAL", 0.3),
        confirm_frames=_int("DETECT_CONFIRM_FRAMES", 2),
        hold_seconds=_float("DETECT_HOLD_SECONDS", 2.0),
        default_auto_fan=_bool("DEFAULT_AUTO_FAN", True),
        default_auto_light=_bool("DEFAULT_AUTO_LIGHT", True),
        default_threshold=_float("DEFAULT_TEMPERATURE_THRESHOLD", 30.0),
        default_absence=_float("DEFAULT_ABSENCE_TIMEOUT", 10.0),
        fan_hysteresis=_float("FAN_HYSTERESIS", 1.0),
        temp_max_age=_float("TEMPERATURE_MAX_AGE", 60.0),
        control_interval=_float("CONTROL_INTERVAL", 1.0),
        log_level=_get("LOG_LEVEL", "INFO").upper(),
    )
