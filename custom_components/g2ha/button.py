from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .coordinator import G2HACoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: G2HACoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([G2HAForceSyncButton(coordinator, entry)])


class G2HAForceSyncButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Force Sync Now"
    _attr_icon = "mdi:sync"

    def __init__(self, coordinator: G2HACoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_force_sync"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="G2HA relay",
            manufacturer="G2HA",
            model="Google Home relay",
            configuration_url="https://github.com/MAFL74/G2HA",
        )

    async def async_press(self) -> None:
        if not await self.coordinator.async_force_sync():
            raise RuntimeError("G2HA relay is not connected")

