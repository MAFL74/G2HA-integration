from types import SimpleNamespace
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .const import DOMAIN, CONF_EXPOSED_ENTITIES, CONF_EXPOSED_AREAS, CONF_EXPOSE_ALL, CONF_EXPOSE_ALL_AREAS
from .coordinator import G2HACoordinator


PLATFORMS = [Platform.SENSOR, Platform.BUTTON]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def handle_set_exposure(call):
        entry_data = hass.data.get(DOMAIN, {})
        coordinator = next((value for value in entry_data.values() if isinstance(value, G2HACoordinator)), None)
        if not coordinator or not getattr(coordinator.entry, "entry_id", None):
            return
        entity_ids = list(dict.fromkeys(call.data.get("entity_ids", [])))
        options = dict(coordinator.entry.options)
        options.update({CONF_EXPOSE_ALL: False, CONF_EXPOSE_ALL_AREAS: False, CONF_EXPOSED_AREAS: [], CONF_EXPOSED_ENTITIES: entity_ids})
        hass.config_entries.async_update_entry(coordinator.entry, options=options)
        coordinator.expose_all = False
        coordinator.expose_all_areas = False
        coordinator.exposed_areas = set()
        coordinator.exposed_entities = set(entity_ids)
        await coordinator.async_force_sync()

    if not hass.services.has_service(DOMAIN, "set_exposure"):
        hass.services.async_register(DOMAIN, "set_exposure", handle_set_exposure, schema=vol.Schema({vol.Required("entity_ids"): [str]}))
    yaml_config = config.get(DOMAIN)
    if yaml_config:
        coordinator = G2HACoordinator(hass, SimpleNamespace(data=yaml_config, entry_id="yaml"))
        await coordinator.async_start()
        hass.data.setdefault(DOMAIN, {})["yaml"] = coordinator
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = G2HACoordinator(hass, entry)
    await coordinator.async_start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(
        entry.add_update_listener(_async_options_updated)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_stop()
    return unload_ok

