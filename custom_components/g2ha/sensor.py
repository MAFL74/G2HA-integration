from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .coordinator import G2HACoordinator

_DEVICE_TYPE_METRICS = {
    "LIGHT", "OUTLET", "SWITCH", "FAN", "BLINDS", "THERMOSTAT",
    "WATERHEATER", "HUMIDIFIER", "DEHUMIDIFIER", "AIRPURIFIER",
    "VACUUM", "LOCK", "TV", "CAMERA", "SENSOR",
}

_DEVICE_TYPE_ICONS = {
    "LIGHT": "mdi:lightbulb",
    "OUTLET": "mdi:power-socket",
    "SWITCH": "mdi:toggle-switch",
    "FAN": "mdi:fan",
    "BLINDS": "mdi:blinds",
    "THERMOSTAT": "mdi:thermostat",
    "WATERHEATER": "mdi:water-boiler",
    "HUMIDIFIER": "mdi:air-humidifier",
    "DEHUMIDIFIER": "mdi:air-humidifier-off",
    "AIRPURIFIER": "mdi:air-purifier",
    "VACUUM": "mdi:robot-vacuum",
    "LOCK": "mdi:lock",
    "TV": "mdi:television",
    "CAMERA": "mdi:cctv",
    "SENSOR": "mdi:eye",
}



async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: G2HACoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        G2HAStatusSensor(coordinator, entry, "connection", "Connection", "mdi:lan-connect"),
        G2HAStatusSensor(coordinator, entry, "relay_address", "Relay address", "mdi:ip-network", "relay_address"),
        G2HAStatusSensor(coordinator, entry, "devices", "Synced devices", "mdi:devices", "count"),
        G2HAStatusSensor(coordinator, entry, "found", "Found supported entities", "mdi:magnify", "found"),
        G2HAStatusSensor(coordinator, entry, "filtered", "Filtered entities", "mdi:filter-off", "filtered"),
        G2HAStatusSensor(coordinator, entry, "last_sync", "Last sync", "mdi:sync"),
        G2HAStatusSensor(coordinator, entry, "sync_progress", "Sync progress", "mdi:progress-clock", "sync_progress"),
        G2HAStatusSensor(coordinator, entry, "sync_status", "Sync status", "mdi:sync-circle", "sync_status"),
        G2HAStatusSensor(coordinator, entry, "sync_current", "Syncing device", "mdi:devices", "sync_current"),
    ]
    for key, label in {
        "LIGHT": "Lights", "OUTLET": "Switches", "SWITCH": "Switches",
        "FAN": "Fans", "BLINDS": "Covers", "THERMOSTAT": "Thermostats",
        "WATERHEATER": "Water heaters", "HUMIDIFIER": "Humidifiers",
        "DEHUMIDIFIER": "Dehumidifiers", "AIRPURIFIER": "Air purifiers",
        "VACUUM": "Vacuums", "LOCK": "Locks", "TV": "Media players",
        "CAMERA": "Cameras", "SENSOR": "Sensors",
    }.items():
        entities.append(G2HAStatusSensor(coordinator, entry, f"type_{key.lower()}", f"Synced {label}", _DEVICE_TYPE_ICONS.get(key, "mdi:home-assistant"), key))
    async_add_entities(entities)


class G2HAStatusSensor(SensorEntity):
    _attr_should_poll = False
    _attr_available = True

    @property
    def available(self) -> bool:
        # Keep the diagnostics visible while the relay reconnects.  The
        # connection sensor itself reports the actual connection state.
        return True

    def __init__(self, coordinator, entry, key, name, icon, metric=None):
        self.coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._metric = metric
        # The relay connection is represented by the sensor value itself.
        # Keep the diagnostic entities present while the websocket reconnects.
        self._attr_available = True
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="G2HA relay",
            manufacturer="G2HA",
            model="Google Home relay",
            configuration_url="https://github.com/MAFL74/G2HA",
        )

    @property
    def native_value(self):
        if self._metric == "count":
            return len(self.coordinator.devices)
        if self._metric == "found":
            return self.coordinator.found_count
        if self._metric == "filtered":
            return self.coordinator.filtered_count
        if self._metric == "found":
            return self.coordinator.found_count
        if self._metric == "filtered":
            return self.coordinator.filtered_count
        if self._metric in ("found", "filtered"):
            return {
                "found": self.coordinator.found_count,
                "synced": len(self.coordinator.devices),
                "filtered": self.coordinator.filtered_count,
            }
        if self._metric in _DEVICE_TYPE_METRICS:
            return f"{len(self._synced_items_for_type())} synced"
        if self._metric == "sync_progress":
            return self.coordinator.sync_progress
        if self._metric == "sync_status":
            return self.coordinator.sync_status
        if self._metric == "sync_current":
            return self.coordinator.sync_current_device or "Idle"
        if self._metric == "relay_address":
            parsed = urlparse(self.coordinator.url)
            host = parsed.hostname or self.coordinator.url
            default_port = 443 if parsed.scheme in ("https", "wss") else 80
            return f"{host}:{parsed.port or default_port}"
        if self._metric:
            return self.coordinator.device_counts.get(self._metric, 0)
        if self._attr_unique_id.endswith("_connection"):
            return self.coordinator.connection_state
        if self._attr_unique_id.endswith("_last_sync"):
            value = self.coordinator.last_sync
            if not value:
                return None
            timezone_name = self.coordinator.hass.config.time_zone or "Europe/Oslo"
            try:
                local_value = value.astimezone(ZoneInfo(timezone_name))
            except (KeyError, ValueError):
                local_value = value.astimezone(ZoneInfo("Europe/Oslo"))
            return local_value.strftime("%d.%m.%Y - %H:%M:%S")
        return None

    @property
    def native_unit_of_measurement(self):
        if self._metric == "sync_progress":
            return "%"
        return "devices" if self._metric == "count" else None

    def _synced_items_for_type(self):
        return [
            item for item in self.coordinator.devices
            if item.get("type", "").rsplit(".", 1)[-1] == self._metric
        ]

    def _synced_names_for_type(self):
        return [
            item.get("name") or item.get("id")
            for item in self._synced_items_for_type()
        ]

    @property
    def extra_state_attributes(self):
        if self._metric == "count":
            synced_devices = self.coordinator.devices
            return {
                "relay_url": self.coordinator.url,
                "instance_id": self.coordinator.instance_id,
                "device_types": self.coordinator.device_counts,
                "inventory": [
                    {
                        "name": item.get("name"),
                        "entity_id": item.get("id"),
                        "type": item.get("type"),
                        "room": item.get("room_hint"),
                        "traits": item.get("traits", []),
                        "exposed": item.get("exposed", False),
                        "available": item.get("available", True),
                    }
                    for item in self.coordinator.inventory
                ],
                "synced_device_names": [
                    item.get("name") or item.get("id")
                    for item in synced_devices
                ],
                "synced_devices": [
                    {
                        "name": item.get("name"),
                        "entity_id": item.get("id"),
                        "type": item.get("type"),
                        "room": item.get("room_hint"),
                        "traits": item.get("traits", []),
                        "exposed": item.get("exposed", False),
                        "available": item.get("available", True),
                        "state": item.get("state", {}),
                    }
                    for item in synced_devices
                ],
            }
        if self._metric in ("found", "filtered"):
            return {
                "found": self.coordinator.found_count,
                "synced": len(self.coordinator.devices),
                "filtered": self.coordinator.filtered_count,
            }
        if self._metric in _DEVICE_TYPE_METRICS:
            items = self._synced_items_for_type()
            return {
                "device_count": len(items),
                "synced_device_names": self._synced_names_for_type(),
                "synced_devices": [
                    {
                        "name": item.get("name"),
                        "entity_id": item.get("id"),
                    }
                    for item in items
                ],
            }
        return None

    async def async_added_to_hass(self) -> None:
        self.coordinator.listeners.append(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._handle_update in self.coordinator.listeners:
            self.coordinator.listeners.remove(self._handle_update)

    @callback
    def _handle_update(self):
        self.async_write_ha_state()


class G2HADeviceSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, entry, device):
        self.coordinator = coordinator
        self.device_id = device["id"]
        self._attr_unique_id = f"{entry.entry_id}_device_{self.device_id}"
        self._attr_name = device.get("name") or self.device_id
        self._attr_icon = "mdi:google-home"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="G2HA relay",
            manufacturer="G2HA",
            model="Google Home relay",
            configuration_url="https://github.com/MAFL74/G2HA",
        )

    @property
    def native_value(self):
        item = next((d for d in self.coordinator.devices if d.get("id") == self.device_id), None)
        if not item:
            return "unavailable"
        state = item.get("state", {})
        if "on" in state:
            return "on" if state["on"] else "off"
        return str(next(iter(state.values()), "available"))

    @property
    def extra_state_attributes(self):
        item = next((d for d in self.coordinator.devices if d.get("id") == self.device_id), {})
        return {
            "entity_id": item.get("id"),
            "type": item.get("type"),
            "room": item.get("room_hint"),
            "traits": item.get("traits", []),
            "available": item.get("available", True),
            "state": item.get("state", {}),
        }

    @callback
    def _handle_update(self):
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self.coordinator.listeners.append(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._handle_update in self.coordinator.listeners:
            self.coordinator.listeners.remove(self._handle_update)

