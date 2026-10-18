"""ThingsBoard MQTT Device API communication for 4 independent virtual devices."""
from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Iterable

import paho.mqtt.client as mqtt

from logic import RoomState, parse_bool

TELEMETRY = "v1/devices/me/telemetry"
ATTRIBUTES = "v1/devices/me/attributes"
ATTR_REQUEST = "v1/devices/me/attributes/request/{id}"
ATTR_RESPONSE = "v1/devices/me/attributes/response/"
RPC_REQUEST = "v1/devices/me/rpc/request/"
RPC_RESPONSE = "v1/devices/me/rpc/response/{id}"

ATTR_TEMPERATURE = "temperatureThreshold"
ATTR_ABSENCE = "absenceTimeout"
ATTR_AUTO_MODE = "autoMode"


def print_attributes_table(device_name: str, mode: str, rows: list[tuple[str, str, str, str]]) -> None:
    """Renders a clean, fixed-width ASCII table (76 columns) for Shared Attributes."""
    if not rows:
        return
    w = 76
    border = "+" + "=" * (w - 2) + "+"
    div = "+----------------------+--------------------+--------------------+---------+"
    title = f"SHARED ATTRIBUTES [{mode.upper()}] - Device: {device_name}"
    lines = [
        border,
        f"| {title:<{w - 4}} |",
        div,
        f"| {'Parameter':<20} | {'Previous':<18} | {'Current':<18} | {'Status':<7} |",
        div,
    ]
    for param, prev, curr, status in rows:
        lines.append(f"| {param:<20} | {prev:<18} | {curr:<18} | {status:<7} |")
    lines.append(border)
    print("\n" + "\n".join(lines), flush=True)


# =========================================================================== #
class TBDevice:
    """Base class for independent MQTT connections with a dedicated Access Token."""

    def __init__(self, name: str, token: str, cfg: Any) -> None:
        self.name = name
        self._cfg = cfg
        self._log = logging.getLogger(name)
        self._connected = threading.Event()
        self._stopping = False
        self._request_id = 0
        self._last_publish: mqtt.MQTTMessageInfo | None = None

        clean_name = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        client_id = f"smartroom-{clean_name}"

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.username_pw_set(token)
        if cfg.tb_tls:
            self._client.tls_set()
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.max_queued_messages_set(200)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def wait_connected(self, timeout: float = 3.0) -> bool:
        return self._connected.wait(timeout)

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> None:
        self._client.connect_async(self._cfg.tb_host, self._cfg.tb_port, self._cfg.tb_keepalive)
        self._client.loop_start()

    def stop(self) -> None:
        self._stopping = True
        if self._last_publish is not None and self._connected.is_set():
            try:
                self._last_publish.wait_for_publish(timeout=2.0)
            except Exception:  # noqa: BLE001
                pass
        self._client.disconnect()
        self._client.loop_stop()

    def publish_telemetry(self, values: dict[str, Any]) -> None:
        self._last_publish = self._client.publish(TELEMETRY, json.dumps(values), qos=1)

    def publish_attributes(self, values: dict[str, Any]) -> None:
        self._client.publish(ATTRIBUTES, json.dumps(values), qos=1)

    def request_shared_attributes(self, keys: str | Iterable[str]) -> None:
        """Requests sharedKeys to fetch Shared Attributes accurately from Server."""
        self._request_id += 1
        key_list = keys if isinstance(keys, str) else ",".join(keys)
        self._client.publish(
            ATTR_REQUEST.format(id=self._request_id),
            json.dumps({"sharedKeys": key_list}),
            qos=1,
        )

    def on_connected(self) -> None:
        pass

    def on_rpc(self, method: str, params: Any) -> dict[str, Any]:
        return {"error": f"Method '{method}' is not supported"}

    def on_attributes(self, attrs: dict[str, Any], is_initial: bool = False) -> None:
        pass

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            self._log.error("MQTT connection failed: %s (check access token)", reason_code)
            return
        client.subscribe([(RPC_REQUEST + "+", 1), (ATTRIBUTES, 1), (ATTR_RESPONSE + "+", 1)])
        self._connected.set()
        try:
            self.on_connected()
        except Exception:  # noqa: BLE001
            self._log.exception("Error in on_connected()")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        self._connected.clear()
        if not self._stopping:
            self._log.warning("MQTT connection lost (%s), reconnecting...", reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8") or "{}")
        except ValueError:
            self._log.warning("Ignoring non-JSON payload on topic %s", msg.topic)
            return

        try:
            if msg.topic.startswith(RPC_REQUEST):
                self._handle_rpc(msg.topic, payload)
            elif msg.topic == ATTRIBUTES or msg.topic.startswith(ATTR_RESPONSE):
                is_response = msg.topic.startswith(ATTR_RESPONSE)
                merged: dict[str, Any] = {}

                # Prioritize 'shared' scope
                if isinstance(payload.get("shared"), dict):
                    merged.update(payload["shared"])
                elif isinstance(payload.get("client"), dict) and not is_response:
                    merged.update(payload["client"])
                elif not is_response and not isinstance(payload.get("shared"), dict) and not isinstance(payload.get("client"), dict):
                    merged = payload

                if merged:
                    self.on_attributes(merged, is_initial=is_response)
        except Exception:  # noqa: BLE001
            self._log.exception("Error handling message on topic %s", msg.topic)

    def _handle_rpc(self, topic: str, payload: dict) -> None:
        request_id = topic.rsplit("/", 1)[-1]
        method, params = payload.get("method", ""), payload.get("params")
        try:
            result = self.on_rpc(method, params)
        except Exception as exc:  # noqa: BLE001
            self._log.exception("Failed to execute RPC '%s'", method)
            result = {"error": str(exc)}
        self._client.publish(RPC_RESPONSE.format(id=request_id), json.dumps(result), qos=1)


# =========================================================================== #
class EnvironmentDevice(TBDevice):
    """A101 Environment Sensor: publishes temp/hum, receives temperatureThreshold."""

    def __init__(self, name: str, token: str, cfg: Any, sensor: Any, room: RoomState) -> None:
        super().__init__(name, token, cfg)
        self._sensor, self._room = sensor, room
        self._interval = cfg.sample_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        super().start()
        self._thread = threading.Thread(target=self._read_loop, name="dht-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 3.0)
        super().stop()

    def on_connected(self) -> None:
        self.publish_attributes({"sensorModel": "DHT11", "sampleInterval": self._interval})
        self.request_shared_attributes(ATTR_TEMPERATURE)

    def on_attributes(self, attrs: dict[str, Any], is_initial: bool = False) -> None:
        old_val = self._room.temperature_threshold
        changed = self._room.apply_config(attrs)
        new_val = self._room.temperature_threshold

        has_key = ATTR_TEMPERATURE in attrs
        if has_key:
            status = "UPDATED" if ATTR_TEMPERATURE in changed else "SYNCED"
            mode = "INITIAL SYNC" if is_initial else "LIVE UPDATE"
            print_attributes_table(
                self.name,
                mode,
                [(ATTR_TEMPERATURE, f"{old_val:.1f} C", f"{new_val:.1f} C", status)],
            )

    def _read_loop(self) -> None:
        from hardware import SensorReadError

        consecutive_errors = 0
        has_logged_first = False

        while not self._stop_event.is_set():
            try:
                temp, hum = self._sensor.read()
                consecutive_errors = 0
            except SensorReadError as exc:
                consecutive_errors += 1
                if consecutive_errors == 3 or consecutive_errors % 10 == 0:
                    self._log.warning("DHT11 read issue (%d attempts): %s (check wiring on GPIO%s)", consecutive_errors, exc, getattr(self._cfg, "dht_pin", 4))
                self._stop_event.wait(2.0)
                continue
            except Exception as exc:
                self._log.exception("Unexpected error in DHT11 reader: %s", exc)
                self._stop_event.wait(2.0)
                continue

            self._room.update_temperature(temp)
            self.publish_telemetry({"temperature": round(temp, 1), "humidity": round(hum, 1)})

            if not has_logged_first:
                has_logged_first = True
                self._log.info("DHT11 operational: Temp=%.1f C | Hum=%.0f%% -> First telemetry sent", temp, hum)
            else:
                self._log.debug("Temp: %.1f C | Hum: %.0f%% -> Telemetry sent", temp, hum)

            self._stop_event.wait(self._interval)


# =========================================================================== #
class PresenceDevice(TBDevice):
    """A101 Presence Sensor: publishes personDetected, receives absenceTimeout."""

    def __init__(self, name: str, token: str, cfg: Any, detector: Any, room: RoomState) -> None:
        super().__init__(name, token, cfg)
        self._detector, self._room = detector, room

    def start(self) -> None:
        super().start()
        self._detector.start(self._on_person_changed)

    def stop(self) -> None:
        self._detector.stop()
        self.publish_telemetry({"personDetected": False})
        super().stop()

    def on_connected(self) -> None:
        self.publish_telemetry({"personDetected": self._detector.person_detected})
        self.request_shared_attributes(ATTR_ABSENCE)

    def on_attributes(self, attrs: dict[str, Any], is_initial: bool = False) -> None:
        old_val = self._room.absence_timeout
        changed = self._room.apply_config(attrs)
        new_val = self._room.absence_timeout

        has_key = ATTR_ABSENCE in attrs
        if has_key:
            status = "UPDATED" if ATTR_ABSENCE in changed else "SYNCED"
            mode = "INITIAL SYNC" if is_initial else "LIVE UPDATE"
            print_attributes_table(
                self.name,
                mode,
                [(ATTR_ABSENCE, f"{old_val:.1f}s", f"{new_val:.1f}s", status)],
            )

    def _on_person_changed(self, detected: bool) -> None:
        self._room.update_person(detected)
        self.publish_telemetry({"personDetected": detected})
        status_text = "PERSON DETECTED" if detected else "ROOM VACANT (CLEAR)"
        self._log.info("Presence: %s -> Telemetry sent", status_text)


# =========================================================================== #
class ActuatorDevice(TBDevice):
    """A101 Light / Fan Actuator: switch control, autoMode, and RPC handling."""

    def __init__(self, name: str, token: str, cfg: Any, switch: Any, room: RoomState, auto_mode: bool = True) -> None:
        super().__init__(name, token, cfg)
        self._switch, self._room = switch, room
        self.auto_mode = auto_mode
        self._lock = threading.Lock()

    @property
    def state(self) -> bool:
        return self._switch.is_on

    def set_state(self, state: bool, source: str = "auto") -> bool:
        with self._lock:
            if state == self._switch.is_on:
                return False
            self._switch.set(state)

        status_str = "ON " if state else "OFF"
        self._log.info("%s -> %s [%s]", self.name.upper(), status_str, source)
        self.publish_telemetry({"state": state})
        return True

    def on_connected(self) -> None:
        self.publish_telemetry({"state": self._switch.is_on})
        self.request_shared_attributes(ATTR_AUTO_MODE)

    def on_attributes(self, attrs: dict[str, Any], is_initial: bool = False) -> None:
        old_mode = self.auto_mode

        mode = "INITIAL SYNC" if is_initial else "LIVE UPDATE"
        if ATTR_AUTO_MODE in attrs:
            new_mode = parse_bool(attrs[ATTR_AUTO_MODE])
            status = "UPDATED" if new_mode != old_mode else "SYNCED"
            if new_mode != old_mode:
                self.auto_mode = new_mode
                self.publish_telemetry({"autoMode": self.auto_mode})
            print_attributes_table(self.name, mode, [(ATTR_AUTO_MODE, str(old_mode), str(self.auto_mode), status)])

    def on_rpc(self, method: str, params: Any) -> dict[str, Any]:
        m = method.lower()
        rpc_log = logging.getLogger("rpc")

        # 1. State query
        if m in ("getstate", "get_state", "getvalue", "get_value", "getstatus", "get_status"):
            rpc_log.info("[%s] RPC %s -> state=%s, autoMode=%s", self.name, method, self.state, self.auto_mode)
            return {"state": self.state, "value": self.state, "autoMode": self.auto_mode}

        # 2. Actuator manual control (setState / setValue / toggle)
        if m in ("setstate", "set_state", "setvalue", "set_value", "toggle"):
            if self.auto_mode:
                rpc_log.warning("[%s] RPC %s rejected: manual control disabled while autoMode is True", self.name, method)
                # Ngay lập tức gửi lại trạng thái thực tế để Widget trên ThingsBoard tự động gạt ngược lại vị trí cũ
                self.publish_telemetry({"state": self.state})
                return {
                    "error": f"Manual control disabled while autoMode is True on {self.name}.",
                    "state": self.state,
                    "value": self.state,
                    "autoMode": self.auto_mode,
                    "success": False,
                }

            target_state = (not self.state) if m == "toggle" else parse_bool(params)
            self.set_state(target_state, f"RPC {method}")
            rpc_log.info("[%s] RPC %s(params=%s) -> state=%s", self.name, method, params, self.state)
            return {"state": self.state, "value": self.state, "autoMode": self.auto_mode, "success": True}

        return super().on_rpc(method, params)

    def stop(self) -> None:
        self.set_state(False, "Shutdown")
        super().stop()

