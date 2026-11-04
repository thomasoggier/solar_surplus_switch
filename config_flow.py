import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_EXPORT_SENSOR,
    CONF_TARGET_SWITCH,
    CONF_POWER_THRESHOLD,
    CONF_DELAY_ON,
    CONF_DELAY_OFF,
    CONF_PRIORITY_SENSOR,
    DEFAULT_POWER_THRESHOLD,
    DEFAULT_DELAY_ON,
    DEFAULT_DELAY_OFF,
)

_LOGGER = logging.getLogger(__name__)

class SolarSurplusSwitchConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Surplus Switch."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(title="Solar Surplus Controller", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EXPORT_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_TARGET_SWITCH): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch")
                ),
                vol.Required(CONF_POWER_THRESHOLD, default=DEFAULT_POWER_THRESHOLD): vol.Coerce(float),
                vol.Required(CONF_DELAY_ON, default=DEFAULT_DELAY_ON): vol.Coerce(int),
                vol.Required(CONF_DELAY_OFF, default=DEFAULT_DELAY_OFF): vol.Coerce(int),
                vol.Optional(CONF_PRIORITY_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])
                ),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return SolarSurplusOptionsFlow()
    
class SolarSurplusOptionsFlow(config_entries.OptionsFlow):
    """Gère les options de configuration de l'intégration."""

    async def async_step_init(self, user_input=None):
        """Gère le formulaire des options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_EXPORT_SENSOR,
                    default=options.get(CONF_EXPORT_SENSOR, data.get(CONF_EXPORT_SENSOR))
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                
                vol.Required(
                    CONF_TARGET_SWITCH,
                    default=options.get(CONF_TARGET_SWITCH, data.get(CONF_TARGET_SWITCH, ""))
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch")),

                vol.Required(
                    CONF_POWER_THRESHOLD,
                    default=options.get(CONF_POWER_THRESHOLD, data.get(CONF_POWER_THRESHOLD, DEFAULT_POWER_THRESHOLD))
                ): vol.Coerce(float),

                vol.Required(
                    CONF_DELAY_ON,
                    default=options.get(CONF_DELAY_ON, data.get(CONF_DELAY_ON, DEFAULT_DELAY_ON))
                ): vol.Coerce(int),

                vol.Required(
                    CONF_DELAY_OFF,
                    default=options.get(CONF_DELAY_OFF, data.get(CONF_DELAY_OFF, DEFAULT_DELAY_OFF))
                ): vol.Coerce(int),

                vol.Optional(
                    CONF_PRIORITY_SENSOR,
                    default=options.get(CONF_PRIORITY_SENSOR, data.get(CONF_PRIORITY_SENSOR, ""))
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)