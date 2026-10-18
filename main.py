"""Smart Room Digital Twin - System entry point on Raspberry Pi.

Usage:
    python main.py                 Run the main control system
    python main.py --preview       Run with live camera preview GUI window
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from typing import Any

# Ensure UTF-8 output on both Windows and Linux terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Default DISPLAY to :0 for Linux/VNC if not set in SSH session
if sys.platform.startswith("linux") and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"

from config import ConfigError, load_config
from hardware import create_hardware
from logic import AutoController, RoomState


# =========================================================================== #
# Standardized Colored Logging
# =========================================================================== #
MODULE_META = {
    "main": ("MAIN", "•", "\033[97m"),
    "env": ("ENV ", "•", "\033[96m"),
    "presence": ("PRES", "•", "\033[95m"),
    "fan": ("FAN ", "•", "\033[94m"),
    "light": ("LGHT", "•", "\033[93m"),
    "ctrl": ("CTRL", "•", "\033[92m"),
    "hw": ("HW  ", "•", "\033[97m"),
    "rpc": ("RPC ", "•", "\033[95m"),
}


class PrettyLogFormatter(logging.Formatter):
    def __init__(self, use_color: bool = True) -> None:
        super().__init__(datefmt="%H:%M:%S")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        tag, icon, color = MODULE_META.get(record.name, (record.name.upper()[:4].ljust(4), "•", "\033[97m"))
        msg = record.getMessage()

        if not self.use_color:
            lvl = f"[{record.levelname[:4]}]" if record.levelname != "INFO" else ""
            return f"[{timestamp}] [{tag}] {icon} {lvl} {msg}".strip()

        lvl_prefix = ""
        if record.levelno >= logging.ERROR:
            lvl_prefix = "\033[91m\033[1m[ERROR]\033[0m "
        elif record.levelno >= logging.WARNING:
            lvl_prefix = "\033[93m\033[1m[WARN]\033[0m "
        elif record.levelno <= logging.DEBUG:
            lvl_prefix = "\033[2m[DEBUG]\033[0m "

        time_part = f"\033[2m[{timestamp}]\033[0m"
        mod_part = f"{color}[{tag}]\033[0m"
        return f"{time_part} {mod_part} {icon} {lvl_prefix}{msg}"


def setup_logging(level_name: str = "INFO") -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    use_color = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else True
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(PrettyLogFormatter(use_color=use_color))
    root.addHandler(handler)
    logging.getLogger("paho").setLevel(logging.WARNING)


# =========================================================================== #
# Visual Tables & Banners (Fixed 76 columns)
# =========================================================================== #
def _mask_token(token: str) -> str:
    return f"{token[:4]}...{token[-4:]}" if len(token) > 8 else ("****" if token else "[MISSING]")


def print_banner(cfg) -> None:
    w = 76
    fan_pins = f"IN1:{cfg.fan_in1}" + (f", IN2:{cfg.fan_in2}" if cfg.fan_in2 else "") + (f", ENA:{cfg.fan_enable}" if cfg.fan_enable else "")

    border = "+" + "=" * (w - 2) + "+"

    def row(text: str) -> str:
        inner = text[: w - 4]
        return f"| {inner:<{w - 4}} |"

    def center(text: str) -> str:
        inner = text[: w - 4]
        return f"| {inner:^{w - 4}} |"

    lines = [
        border,
        center("SMART ROOM DIGITAL TWIN"),
        center("Raspberry Pi 4B  *  ThingsBoard MQTT  *  Edge AI"),
        border,
        row(f"Broker     : {cfg.tb_host}:{cfg.tb_port} (TLS: {cfg.tb_tls})"),
        row(f"Tokens     : env:[{_mask_token(cfg.token_environment)}] pres:[{_mask_token(cfg.token_presence)}]"),
        row(f"             fan:[{_mask_token(cfg.token_fan)}] light:[{_mask_token(cfg.token_light)}]"),
        row(f"Pinout     : DHT=GPIO{cfg.dht_pin} | LED=GPIO{cfg.led_pin} | FAN=GPIO({fan_pins})"),
        row(f"Defaults   : Threshold={cfg.default_threshold:.1f} C | Absence={cfg.default_absence:.1f}s | Hysteresis={cfg.fan_hysteresis:.1f} C"),
        row(f"Auto Mode  : Fan={cfg.default_auto_fan} | Light={cfg.default_auto_light} | Preview={cfg.camera_preview} | PID={os.getpid()}"),
        border,
    ]
    try:
        print("\n" + "\n".join(lines), flush=True)
    except Exception:
        print(f"[Smart Room] Broker: {cfg.tb_host}:{cfg.tb_port} | PID: {os.getpid()}")


def print_connection_table(cfg, devices: list[Any]) -> None:
    w = 76
    border = "+" + "=" * (w - 2) + "+"
    div = "+--------------------+---------------------+-----------------+-------------+"
    title = f"MQTT CONNECTION STATUS : {cfg.tb_host}:{cfg.tb_port}"

    lines = [
        border,
        f"| {title:<{w - 4}} |",
        div,
        f"| {'Device Role':<18} | {'Client ID':<19} | {'Access Token':<15} | {'Status':<11} |",
        div,
    ]

    roles = {
        "env": ("Environment (DHT)", cfg.token_environment),
        "presence": ("Presence (Camera)", cfg.token_presence),
        "fan": ("DC Fan Actuator", cfg.token_fan),
        "light": ("Light Actuator", cfg.token_light),
    }

    for d in devices:
        role, tok = roles.get(d.name, (d.name.capitalize(), ""))
        status = "ONLINE [OK]" if d.is_connected else "CONNECTING..."
        clean_name = d.name.lower()
        client_id = f"smartroom-{clean_name}"
        lines.append(f"| {role:<18} | {client_id:<19} | {_mask_token(tok):<15} | {status:<11} |")

    lines.append(border)
    print("\n" + "\n".join(lines) + "\n", flush=True)


def acquire_lock():
    try:
        import fcntl
        lock_file = open("/tmp/smart_room.lock", "w")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except (ImportError, OSError):
        return None


# =========================================================================== #
# System Lifecycle
# =========================================================================== #
def run_app(cfg) -> int:
    from thingsboard import ActuatorDevice, EnvironmentDevice, PresenceDevice

    lock = acquire_lock()
    print_banner(cfg)

    log = logging.getLogger("main")
    hw = create_hardware(cfg)
    room = RoomState(cfg.default_threshold, cfg.default_absence)

    env = EnvironmentDevice("env", cfg.token_environment, cfg, hw["sensor"], room)
    presence = PresenceDevice("presence", cfg.token_presence, cfg, hw["detector"], room)
    fan = ActuatorDevice("fan", cfg.token_fan, cfg, hw["fan"], room, auto_mode=cfg.default_auto_fan)
    light = ActuatorDevice("light", cfg.token_light, cfg, hw["light"], room, auto_mode=cfg.default_auto_light)

    controller = AutoController(room, light, fan, cfg.fan_hysteresis, cfg.temp_max_age, cfg.control_interval)
    devices = [env, presence, fan, light]

    stop_event = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())

    for d in devices:
        d.start()

    # Wait up to 3 seconds for initial MQTT connection handshakes
    for d in devices:
        d.wait_connected(timeout=3.0)

    print_connection_table(cfg, devices)
    controller.start()

    log.info("System ready and operational. Press Ctrl+C to exit.")

    detector = hw.get("detector")
    if cfg.camera_preview and detector and hasattr(detector, "render_preview"):
        log.info("Camera GUI preview active (press 'q' on preview window or Ctrl+C to exit)...")
        while not stop_event.is_set():
            if not detector.render_preview():
                break
    else:
        stop_event.wait()

    log.info("Stopping system...")
    controller.stop()
    for d in devices:
        try:
            d.stop()
        except Exception:  # noqa: BLE001
            pass
    for k in ("sensor", "fan", "light"):
        try:
            hw[k].close()
        except Exception:  # noqa: BLE001
            pass
    if lock:
        try:
            lock.close()
        except Exception:  # noqa: BLE001
            pass
    log.info("System stopped gracefully.")
    return 0


def main() -> int:
    import dataclasses

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--preview", "--camera-preview", action="store_true", help="Enable live camera preview GUI window on Pi (VNC/HDMI)")
    args = parser.parse_args()

    cfg = load_config()
    if args.preview:
        cfg = dataclasses.replace(cfg, camera_preview=True)

    setup_logging(cfg.log_level)

    try:
        cfg.validate()
    except ConfigError as exc:
        logging.getLogger("main").error("%s", exc)
        return 2

    return run_app(cfg)


if __name__ == "__main__":
    sys.exit(main())

