DOMAIN = "g2ha"
CONF_RELAY_URL = "relay_url"
CONF_INSTANCE_ID = "instance_id"
CONF_EXPOSED_ENTITIES = "exposed_entities"
CONF_EXPOSED_AREAS = "exposed_areas"
CONF_EXPOSE_ALL_AREAS = "expose_all_areas"
CONF_EXPOSE_ALL = "expose_all"
CONF_INCLUDE_UNAVAILABLE = "include_unavailable"
CONF_ROOM_NAMING_MODE = "room_naming_mode"
CONF_ROOM_NAME_MAP = "room_name_map"
CONF_HOME_NAME = "home_name"
ROOM_NAMING_HA = "ha"
ROOM_NAMING_GOOGLE = "google"
ROOM_NAMING_CUSTOM = "custom"
DEFAULT_RELAY_URL = ""

# Domains that G2HA can translate into Google Home device types. Keeping this
# list in one place also lets the options flow offer a searchable entity picker
# instead of asking users to paste hundreds of entity IDs.
SUPPORTED_DOMAINS = [
    "light",
    "switch",
    "input_boolean",
    "fan",
    "cover",
    "climate",
    "water_heater",
    "humidifier",
    "dehumidifier",
    "air_purifier",
    "vacuum",
    "lock",
    "media_player",
    "camera",
    "sensor",
    "binary_sensor",
]

