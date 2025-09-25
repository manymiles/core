"""The Uniden Scanner integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ADDONS_COORDINATOR

_LOGGER = logging.getLogger(__name__)


# The list of platforms that the integration supports.
PLATFORMS = ["media_player"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Uniden Scanner from a config entry."""
    # _LOGGER.debug("Setting up Uniden Scanner integration from a config entry")

    # Store the config entry data for use by other platforms
    hass.data.setdefault(entry.domain, {})[entry.entry_id] = entry.data

    # Forward the setup to the media_player platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Pop add-on data
    hass.data.pop(ADDONS_COORDINATOR, None)

    return unload_ok
