from homeassistant import config_entries
import voluptuous as vol
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_EXPOSED_ENTITIES,
    CONF_INSTANCE_ID,
    CONF_RELAY_URL,
    CONF_HOME_NAME,
    DEFAULT_RELAY_URL,
    DOMAIN,
)

CONF_EXPOSE_ALL = "expose_all"
CONF_EXPOSED_AREAS = "exposed_areas"
CONF_EXPOSE_ALL_AREAS = "expose_all_areas"
CONF_INCLUDE_UNAVAILABLE = "include_unavailable"
CONF_ROOM_NAME_MAP = "room_name_map"
CONF_ROOM_NAMING_MODE = "room_naming_mode"
ROOM_NAMING_HA = "ha"
ROOM_NAMING_GOOGLE = "google"
ROOM_NAMING_CUSTOM = "custom"
SUPPORTED_DOMAINS = [
    "light", "switch", "input_boolean", "fan", "cover", "climate",
    "water_heater", "humidifier", "dehumidifier", "air_purifier", "vacuum",
    "lock", "media_player", "camera", "sensor", "binary_sensor",
]


class G2HAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return G2HAOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            await self.async_set_unique_id(user_input[CONF_INSTANCE_ID])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="G2HA", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_RELAY_URL, default=DEFAULT_RELAY_URL): str,
                vol.Required(CONF_INSTANCE_ID, default="home"): str,
            }),
            errors=errors,
        )


class G2HAOptionsFlow(config_entries.OptionsFlow):
    def _current_entities(self) -> list[str]:
        value = self.config_entry.options.get(
            CONF_EXPOSED_ENTITIES,
            self.config_entry.data.get(CONF_EXPOSED_ENTITIES, ""),
        )
        if isinstance(value, str):
            value = value.replace(",", "\n").splitlines()
        return sorted({item.strip() for item in (value or []) if item and item.strip()})

    def _current_areas(self) -> list[str]:
        value = self.config_entry.options.get(CONF_EXPOSED_AREAS, [])
        if isinstance(value, str):
            value = value.replace(",", "\n").splitlines()
        return sorted({item.strip() for item in (value or []) if item and item.strip()})

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            self._pending_options = dict(user_input)
            if user_input[CONF_EXPOSE_ALL]:
                self._pending_options[CONF_EXPOSED_ENTITIES] = []
                return self.async_create_entry(title="", data=self._pending_options)
            return await self.async_step_entities()

        current = self._current_entities()
        expose_all = self.config_entry.options.get(CONF_EXPOSE_ALL, not current)
        expose_all_areas = self.config_entry.options.get(CONF_EXPOSE_ALL_AREAS, False)
        include_unavailable = self.config_entry.options.get(CONF_INCLUDE_UNAVAILABLE, True)
        room_naming_mode = self.config_entry.options.get(CONF_ROOM_NAMING_MODE, ROOM_NAMING_HA)
        room_name_map = self.config_entry.options.get(CONF_ROOM_NAME_MAP, "")
        home_name = self.config_entry.options.get(CONF_HOME_NAME, "")
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_EXPOSE_ALL, default=expose_all): bool,
                vol.Required(CONF_EXPOSE_ALL_AREAS, default=expose_all_areas): bool,
                vol.Required(CONF_INCLUDE_UNAVAILABLE, default=include_unavailable): bool,
                vol.Optional(
                    CONF_EXPOSED_AREAS,
                    default=self._current_areas(),
                ): selector.AreaSelector(
                    selector.AreaSelectorConfig(multiple=True)
                ),
                vol.Required(CONF_ROOM_NAMING_MODE, default=room_naming_mode): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[
                        {"value": ROOM_NAMING_HA, "label": "Bruk HA-områdenavn"},
                        {"value": ROOM_NAMING_GOOGLE, "label": "La Google Home styre romnavn"},
                        {"value": ROOM_NAMING_CUSTOM, "label": "Bruk egendefinert mapping"},
                    ])
                ),
                vol.Optional(CONF_ROOM_NAME_MAP, default=room_name_map): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Optional(CONF_HOME_NAME, default=home_name): selector.TextSelector(
                    selector.TextSelectorConfig(type="text")
                ),
            }),
        )

    async def async_step_entities(self, user_input=None):
        if user_input is not None:
            options = dict(getattr(self, "_pending_options", {}))
            options[CONF_EXPOSED_ENTITIES] = user_input.get(CONF_EXPOSED_ENTITIES, [])
            options[CONF_EXPOSE_ALL] = False
            return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="entities",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_EXPOSED_ENTITIES,
                    default=self._current_entities(),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=SUPPORTED_DOMAINS,
                        multiple=True,
                    )
                ),
            }),
        )

