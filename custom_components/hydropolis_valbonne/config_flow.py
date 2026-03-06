from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HydropolisValbonneApi, HydropolisValbonneAuthError, HydropolisValbonneApiError
from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class HydropolisValbonneConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hydropolis Valbonne."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME])
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api = HydropolisValbonneApi(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                session=session,
            )

            try:
                await api.async_validate_credentials()
            except HydropolisValbonneAuthError:
                errors["base"] = "invalid_auth"
            except HydropolisValbonneApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
