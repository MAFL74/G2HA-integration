import asyncio
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from aiohttp import ClientSession, WSMsgType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CONF_EXPOSED_ENTITIES, CONF_INSTANCE_ID, CONF_RELAY_URL, CONF_HOME_NAME

CONF_EXPOSE_ALL = "expose_all"
CONF_EXPOSED_AREAS = "exposed_areas"
CONF_EXPOSE_ALL_AREAS = "expose_all_areas"
CONF_INCLUDE_UNAVAILABLE = "include_unavailable"
CONF_ROOM_NAME_MAP = "room_name_map"
CONF_ROOM_NAMING_MODE = "room_naming_mode"
ROOM_NAMING_GOOGLE = "google"

_LOGGER = logging.getLogger(__name__)


# Google Smart Home device types are capability based.  Keep the domain to
# type mapping separate from the state/command mapping so new HA domains can
# be added without changing the relay protocol.
_DOMAIN_TYPES = {
    "light": "LIGHT",
    "switch": "OUTLET",
    "input_boolean": "SWITCH",
    "fan": "FAN",
    "cover": "BLINDS",
    "climate": "THERMOSTAT",
    "water_heater": "WATERHEATER",
    "humidifier": "HUMIDIFIER",
    "dehumidifier": "DEHUMIDIFIER",
    "air_purifier": "AIRPURIFIER",
    "vacuum": "VACUUM",
    "lock": "LOCK",
    "media_player": "TV",
    "camera": "CAMERA",
    "scene": "SCENE",
    "sensor": "SENSOR",
    "binary_sensor": "SENSOR",
}

_GOOGLE = "action.devices."
_GOOGLE_HVAC_MODE_MAP = {
    "heat_cool": "heatcool",
    "fan_only": "fan-only",
}
_HA_HVAC_MODE_MAP = {google: ha for ha, google in _GOOGLE_HVAC_MODE_MAP.items()}


class G2HACoordinator:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.url = entry.data[CONF_RELAY_URL]
        self.instance_id = entry.data[CONF_INSTANCE_ID]
        options = getattr(entry, "options", {})
        configured_exposure = options.get(
            CONF_EXPOSED_ENTITIES,
            entry.data.get(CONF_EXPOSED_ENTITIES, ""),
        )
        if isinstance(configured_exposure, str):
            configured_exposure = configured_exposure.replace(",", "\n").splitlines()
        self.exposed_entities = {
            entity_id.strip()
            for entity_id in (configured_exposure or [])
            if entity_id and entity_id.strip()
        }
        configured_areas = options.get(CONF_EXPOSED_AREAS, [])
        if isinstance(configured_areas, str):
            configured_areas = configured_areas.replace(",", "\n").splitlines()
        self.exposed_areas = {
            area_id.strip()
            for area_id in (configured_areas or [])
            if area_id and area_id.strip()
        }
        self.expose_all_areas = options.get(CONF_EXPOSE_ALL_AREAS, False)
        self.expose_all = options.get(CONF_EXPOSE_ALL, not self.exposed_entities)
        self.include_unavailable = options.get(CONF_INCLUDE_UNAVAILABLE, True)
        self.room_naming_mode = options.get(CONF_ROOM_NAMING_MODE, "ha")
        self.room_name_map = self._parse_room_map(options.get(CONF_ROOM_NAME_MAP, ""))
        self.home_name = str(options.get(CONF_HOME_NAME, "")).strip()
        self.entity_registry = er.async_get(hass)
        self.device_registry = dr.async_get(hass)
        self.area_registry = ar.async_get(hass)
        self.session: ClientSession | None = None
        self.ws = None
        self.task: asyncio.Task | None = None
        self.resync_task: asyncio.Task | None = None
        self.unsub = None
        self.devices: list[dict[str, Any]] = []
        self.inventory: list[dict[str, Any]] = []
        self.last_sync: datetime | None = None
        self.last_connection: datetime | None = None
        self.connection_state = "disconnected"
        self.listeners: list[Callable[[], None]] = []
        self.entity_adders: list[Callable[[list[Any]], None]] = []
        self.sync_progress = 0
        self.sync_current_device = ""
        self.sync_processed = 0
        self.sync_total = 0
        self.sync_status = "Idle"
        self.sync_error = ""

    async def async_start(self) -> None:
        self.session = ClientSession()
        self.unsub = self.hass.bus.async_listen("state_changed", self._state_changed)
        self.task = asyncio.create_task(self._run(), name="g2ha-relay")

    async def async_stop(self) -> None:
        if self.unsub:
            self.unsub()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.resync_task:
            self.resync_task.cancel()
            await asyncio.gather(self.resync_task, return_exceptions=True)
        if self.session:
            await self.session.close()

    async def _run(self) -> None:
        assert self.session
        while True:
            try:
                async with self.session.ws_connect(f"{self.url}?instance_id={self.instance_id}", heartbeat=30) as ws:
                    self.ws = ws
                    self.connection_state = "connected"
                    self.last_connection = datetime.now(timezone.utc)
                    await ws.send_json({"type": "hello", "payload": {"source": "home_assistant"}})
                    self.sync_status = "Syncing"
                    self.sync_progress = 0
                    self.sync_error = ""
                    self.devices = self._devices()
                    self.last_sync = datetime.now(timezone.utc)
                    if getattr(self.entry, "entry_id", "") != "yaml":
                        self.hass.config_entries.async_update_entry(
                            self.entry,
                            title=f"G2HA · {len(self.devices)} enheter · tilkoblet",
                        )
                    await ws.send_json({"type": "devices", "devices": self.devices})
                    self._sync_complete()
                    for adder in tuple(self.entity_adders):
                        adder(self.devices)
                    self._notify_listeners()
                    self.resync_task = asyncio.create_task(self._resync_loop(ws), name="g2ha-resync")
                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            message = msg.json()
                            if message.get("type") == "execute":
                                try:
                                    commands = await asyncio.wait_for(self._execute(message.get("payload", {})), timeout=12)
                                except Exception as err:
                                    _LOGGER.exception("G2HA execute failed: %s", err)
                                    commands = [{"ids": [], "status": "ERROR"}]
                                await ws.send_json({"type": "result", "request_id": message.get("request_id"), "payload": {"commands": commands}})
                        elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.warning("G2HA relay connection failed: %s", err)
            finally:
                if self.resync_task:
                    self.resync_task.cancel()
                    await asyncio.gather(self.resync_task, return_exceptions=True)
                    self.resync_task = None
                self.ws = None
                self.connection_state = "disconnected"
                self._notify_listeners()
            await asyncio.sleep(10)

    async def _resync_loop(self, ws) -> None:
        await asyncio.sleep(5)
        while ws is self.ws:
            devices = self._devices()
            if [item.get("id") for item in devices] != [item.get("id") for item in self.devices]:
                self.devices = devices
                self.last_sync = datetime.now(timezone.utc)
                await ws.send_json({"type": "devices", "devices": self.devices})
                for adder in tuple(self.entity_adders):
                    adder(self.devices)
                self._notify_listeners()
            await asyncio.sleep(30)

    @property
    def device_counts(self) -> dict[str, int]:
        return dict(Counter(item["type"].rsplit(".", 1)[-1] for item in self.devices))

    @property
    def found_count(self) -> int:
        """Number of entities that are supported by G2HA before exposure filtering."""
        return len(self.inventory)

    @property
    def filtered_count(self) -> int:
        """Number of supported entities excluded from the synchronized device list."""
        return max(0, self.found_count - len(self.devices))

    def _notify_listeners(self) -> None:
        for listener in tuple(self.listeners):
            listener()

    def register_entity_adder(self, adder: Callable[[list[Any]], None]) -> None:
        self.entity_adders.append(adder)

    def unregister_entity_adder(self, adder: Callable[[list[Any]], None]) -> None:
        if adder in self.entity_adders:
            self.entity_adders.remove(adder)

    async def async_force_sync(self) -> bool:
        """Immediately publish the complete current inventory to the relay."""
        if not self.ws or self.ws.closed:
            return False
        self.sync_status = "Syncing"
        self.sync_progress = 0
        self.sync_error = ""
        self.devices = self._devices()
        self.last_sync = datetime.now(timezone.utc)
        await self.ws.send_json({"type": "devices", "devices": self.devices})
        self._sync_complete()
        for adder in tuple(self.entity_adders):
            adder(self.devices)
        self._notify_listeners()
        return True

    def _sync_complete(self) -> None:
        self.sync_progress = 100
        self.sync_processed = self.sync_total
        self.sync_current_device = ""
        self.sync_status = "Completed"
        self._notify_listeners()

    def _devices(self) -> list[dict[str, Any]]:
        result = []
        inventory = []
        states = self.hass.states.async_all()
        self.sync_total = len(states)
        self.sync_processed = 0
        for state in states:
            self.sync_current_device = state.name or state.entity_id
            self.sync_processed += 1
            self.sync_progress = int(self.sync_processed * 100 / self.sync_total) if self.sync_total else 100
            if not self.include_unavailable and state.state in ("unknown", "unavailable"):
                continue
            try:
                item = self._map_state(state)
            except Exception:
                _LOGGER.exception("Could not map HA entity %s; skipping it", state.entity_id)
                continue
            if item:
                area_id = self._area_id(state.entity_id)
                exposed = self.expose_all or state.entity_id in self.exposed_entities or area_id in self.exposed_areas or (self.expose_all_areas and area_id)
                item["exposed"] = exposed
                inventory.append(item)
                if exposed:
                    result.append(item)
        self.inventory = inventory
        return result

    def _map_state(self, state) -> dict[str, Any] | None:
        domain = state.domain
        device_type = _DOMAIN_TYPES.get(domain)
        if not device_type:
            return None
        traits = self._traits_for_state(state)
        if not traits:
            return None
        room_hint = self._room_name(state.entity_id)
        if self.room_naming_mode != ROOM_NAMING_GOOGLE and not room_hint:
            room_hint = state.attributes.get("room_name")
        attributes = {}
        if domain == "climate":
            modes = state.attributes.get("hvac_modes", [])
            attributes = {
                "availableThermostatModes": [self._google_hvac_mode(mode) for mode in modes],
                "thermostatTemperatureUnit": "C",
            }
        return {"id": state.entity_id, "type": f"{_GOOGLE}types.{device_type}", "name": state.name, "room_hint": room_hint, "home_name": self.home_name, "traits": traits, "attributes": attributes, "available": state.state not in ("unknown", "unavailable"), "state": self._state_payload(state)}

    def _area_id(self, entity_id: str) -> str | None:
        entity = self.entity_registry.async_get(entity_id)
        if not entity:
            return None
        if entity.area_id:
            return entity.area_id
        if entity.device_id:
            device = self.device_registry.async_get(entity.device_id)
            return device.area_id if device else None
        return None

    def _room_name(self, entity_id: str) -> str | None:
        if self.room_naming_mode == ROOM_NAMING_GOOGLE:
            return None
        area_id = self._area_id(entity_id)
        if not area_id:
            return self._room_from_name(entity_id)

        # The AreaRegistry API has changed between HA releases.  Some
        # versions expose async_get_area(), while others route that method
        # through a removed async_get() helper.  Read the registry data
        # directly first so room hints work across both API shapes.
        area = None
        area_data = getattr(self.area_registry, "_area_data", None)
        if isinstance(area_data, dict):
            area = area_data.get(area_id)
        if area is None:
            areas = getattr(self.area_registry, "areas", None)
            if areas is not None:
                try:
                    area = areas.get(area_id)
                except AttributeError:
                    try:
                        area = areas[area_id]
                    except (KeyError, TypeError):
                        area = None
        if not area:
            return self._room_from_name(entity_id)
        return self.room_name_map.get(area_id) or self.room_name_map.get(area.name) or area.name

    def _room_from_name(self, entity_id: str) -> str | None:
        """Infer a room from the conventional HA name 'Room - Device'."""
        state = self.hass.states.get(entity_id)
        name = (state.name if state else "").strip()
        if " - " not in name:
            return None
        prefix = name.split(" - ", 1)[0].strip()
        return prefix or None

    @staticmethod
    def _google_hvac_mode(value: Any) -> str:
        """Translate Home Assistant HVAC mode names to Google's vocabulary."""
        mode = str(value).strip().lower()
        return _GOOGLE_HVAC_MODE_MAP.get(mode, mode)

    @staticmethod
    def _parse_room_map(value: Any) -> dict[str, str]:
        if not isinstance(value, str):
            return {}
        result: dict[str, str] = {}
        for line in value.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            separator = "=" if "=" in line else "->" if "->" in line else None
            if not separator:
                continue
            source, target = (part.strip() for part in line.split(separator, 1))
            if source and target:
                result[source] = target
        return result

    def _traits_for_state(self, state) -> list[str]:
        domain = state.domain
        attrs = state.attributes
        traits: list[str] = []
        if domain in ("light", "switch", "input_boolean", "fan", "humidifier", "dehumidifier", "air_purifier", "media_player"):
            traits.append(f"{_GOOGLE}traits.OnOff")
        if domain == "light" and ("brightness" in attrs or "supported_color_modes" in attrs):
            traits.append(f"{_GOOGLE}traits.Brightness")
        if domain == "light" and ("rgb_color" in attrs or "hs_color" in attrs or "color_temp" in attrs):
            traits.append(f"{_GOOGLE}traits.ColorSetting")
        if domain == "fan":
            traits.append(f"{_GOOGLE}traits.FanSpeed")
        if domain == "cover":
            traits.append(f"{_GOOGLE}traits.OpenClose")
        if domain in ("climate", "water_heater"):
            traits.append(f"{_GOOGLE}traits.TemperatureSetting")
        if domain == "lock":
            traits.append(f"{_GOOGLE}traits.LockUnlock")
        if domain == "vacuum":
            traits.extend((f"{_GOOGLE}traits.StartStop", f"{_GOOGLE}traits.Modes"))
        if domain == "media_player":
            traits.extend((f"{_GOOGLE}traits.TransportControl", f"{_GOOGLE}traits.Volume", f"{_GOOGLE}traits.MediaState"))
        if domain == "camera":
            traits.append(f"{_GOOGLE}traits.CameraStream")
        if domain in ("sensor", "binary_sensor"):
            traits.append(f"{_GOOGLE}traits.SensorState")
        if domain == "scene":
            traits = []
        return list(dict.fromkeys(traits))

    def _state_payload(self, state) -> dict[str, Any]:
        value = state.state
        if state.domain in ("light", "switch", "fan"):
            return {"on": value == "on"}
        if state.domain in ("input_boolean", "humidifier", "dehumidifier", "air_purifier"):
            return {"on": value not in ("off", "idle", "standby")}
        if state.domain == "cover":
            position = state.attributes.get("current_position")
            try:
                position = max(0, min(100, int(position))) if position is not None else (0 if value == "closed" else 100)
            except (TypeError, ValueError):
                position = 0 if value == "closed" else 100
            return {"openPercent": position}
        if state.domain == "lock":
            return {"isLocked": value == "locked"}
        if state.domain == "climate":
            return {
                "thermostatMode": self._google_hvac_mode(state.state),
                "thermostatTemperatureSetpoint": state.attributes.get("temperature"),
            }
        if state.domain == "water_heater":
            return {
                "thermostatMode": self._google_hvac_mode(state.attributes.get("operation_mode", state.state)),
                "thermostatTemperatureSetpoint": state.attributes.get("temperature"),
            }
        if state.domain == "media_player":
            playback_state = {
                "playing": "PLAYING",
                "paused": "PAUSED",
                "buffering": "BUFFERING",
                "off": "STOPPED",
            }.get(state.state, "STOPPED")
            return {
                "on": state.state not in ("off", "idle", "standby"),
                "activityState": "ACTIVE" if state.state in ("playing", "paused", "buffering") else "INACTIVE",
                "playbackState": playback_state,
            }
        if state.domain in ("sensor", "binary_sensor"):
            value = state.state
            try:
                value = float(value)
            except (TypeError, ValueError):
                pass
            return {"currentSensorStateData": [{"name": "currentStatus", "currentState": value}]}
        return {}

    @callback
    def _state_changed(self, event: Event) -> None:
        if not self.ws:
            return
        state = event.data.get("new_state")
        if state:
            asyncio.create_task(self.ws.send_json({"type": "state", "device_id": state.entity_id, "payload": self._state_payload(state)}))

    async def _execute(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        commands = []
        for command in payload.get("commands", []):
            devices = command.get("devices", {})
            device_ids = devices.get("ids", []) if isinstance(devices, dict) else devices
            for raw_entity_id in device_ids:
                entity_id = raw_entity_id.get("id") if isinstance(raw_entity_id, dict) else raw_entity_id
                if not isinstance(entity_id, str) or "." not in entity_id:
                    commands.append({"ids": [entity_id], "status": "ERROR"})
                    continue
                for execution in command.get("execution", []):
                    try:
                        result = await self._call_service(entity_id, execution.get("command"), execution.get("params", {}))
                    except Exception as err:
                        _LOGGER.exception("G2HA service call failed for %s: %s", entity_id, err)
                        result = False
                    commands.append({"ids": [entity_id], "status": "SUCCESS" if result else "ERROR"})
        return commands

    async def _call_service(self, entity_id: str, command: str | None, params: dict[str, Any]) -> bool:
        domain = entity_id.split(".", 1)[0]
        service = None
        data: dict[str, Any] = {"entity_id": entity_id}
        if command == "action.devices.commands.OnOff":
            service = "turn_on" if params.get("on") else "turn_off"
        elif command == "action.devices.commands.BrightnessAbsolute":
            service, data["brightness_pct"] = "turn_on", params.get("brightness", 100)
        elif command == "action.devices.commands.OpenClose":
            service = "open_cover" if params.get("openPercent", 0) else "close_cover"
        elif command == "action.devices.commands.LockUnlock":
            service = "lock" if params.get("lock") else "unlock"
        elif command == "action.devices.commands.ThermostatTemperatureSetpoint":
            service, data["temperature"] = "set_temperature", params.get("thermostatTemperatureSetpoint")
        elif command == "action.devices.commands.ThermostatSetMode":
            google_mode = str(params.get("thermostatMode", "off")).lower()
            service, data["hvac_mode"] = "set_hvac_mode", _HA_HVAC_MODE_MAP.get(google_mode, google_mode)
        elif command == "action.devices.commands.StartStop":
            service = "start" if params.get("start") else "stop"
        elif command == "action.devices.commands.MediaPause":
            service = "media_pause"
        elif command == "action.devices.commands.MediaResume":
            service = "media_play"
        elif command == "action.devices.commands.SetVolume":
            service, data["volume_level"] = "volume_set", params.get("volumeLevel", 0)
        elif command == "action.devices.commands.SelectChannel":
            service, data["channel"] = "select_source", params.get("channelCode")
        elif command == "action.devices.commands.SelectInput":
            service, data["source"] = "select_source", params.get("newInput")
        if not service:
            return False
        await self.hass.services.async_call(domain, service, data, blocking=True)
        return True

