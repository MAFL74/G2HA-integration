from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "integration": {
            "domain": DOMAIN,
            "version": "0.2.0",
            "entry_id": entry.entry_id,
            "instance_id": coordinator.instance_id,
            "relay_url": coordinator.url,
        },
        "connection": {
            "state": coordinator.connection_state,
            "last_connection": coordinator.last_connection,
            "last_sync": coordinator.last_sync,
        },
        "summary": {
            "device_count": len(coordinator.devices),
            "found_count": coordinator.found_count,
            "filtered_count": coordinator.filtered_count,
            "device_types": coordinator.device_counts,
        },
        "devices": [
            {
                "name": item.get("name"),
                "entity_id": item.get("id"),
                "type": item.get("type"),
                "room": item.get("room_hint"),
                "traits": item.get("traits", []),
                "state": item.get("state", {}),
            }
            for item in coordinator.devices
        ],
    }

