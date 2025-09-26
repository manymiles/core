"""Config flow for Uniden Scanner integration."""

# Implements the config flow for the Uniden Scanner component.

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import selector

from .const import DOMAIN

# Define the user data schema for the config flow
DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("Scanner Name", default="Uniden Scanner"): str,
        vol.Required("Scanner IP Address", default="10.0.0.1"): str,
        vol.Required("Scanner IP Port", default=50536): int,
        vol.Required("Scanner Model", default="SDS200"): selector(
            {
                "select": {
                    "options": [
                        "SDS100",
                        "SDS200",
                    ]
                }
            }
        ),
        vol.Optional("Polling Time", default=5): int,
    }
)


class UnidenScannerConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Uniden Scanner."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Handle the initial step."""
        # errors = {}
        if user_input is not None:
            # We will use this in future steps to validate the connection
            # to the scanner. For now, we just validate the input format.
            # _LOGGER = logging.getLogger(__name__)
            # _LOGGER.warning(f"User input received: {user_input}")
            user_title = user_input.get("Scanner Name", "Uniden Scanner")
            return self.async_create_entry(title=user_title, data=user_input)

        return self.async_show_form(
            data_schema=DATA_SCHEMA,
            errors={},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            # Update the entry with new data
            return self.async_update_reload_and_abort(
                entry,
                data_updates=user_input,
            )

        # Show the form pre-filled with existing config data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, entry.data),
        )
