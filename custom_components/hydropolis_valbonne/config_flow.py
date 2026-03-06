"""Config flow for Hydropolis Valbonne integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HydropolisApiError, HydropolisAuthError, HydropolisClient, HydropolisContract
from .const import CONF_CONTRAT_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class HydropolisConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hydropolis Valbonne."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
        self._username: str = ""
        self._password: str = ""
        self._contracts: list[HydropolisContract] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the credentials step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            session = async_get_clientsession(self.hass)
            client = HydropolisClient(session, self._username, self._password)

            try:
                if not await client.authenticate():
                    errors["base"] = "invalid_auth"
                else:
                    self._contracts = await client.get_contracts()
                    if not self._contracts:
                        errors["base"] = "no_contracts"
                    elif len(self._contracts) == 1:
                        contract = self._contracts[0]
                        return await self._create_entry(contract)
                    else:
                        return await self.async_step_select_contract()
            except AbortFlow:
                raise
            except HydropolisApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during authentication")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_select_contract(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick a contract when multiple are available."""
        if user_input is not None:
            selected_id = user_input[CONF_CONTRAT_ID]
            contract = next(
                (c for c in self._contracts if c.contrat_id == selected_id), None
            )
            if contract is None:
                return self.async_abort(reason="unknown")
            return await self._create_entry(contract)

        options = {
            c.contrat_id: f"{c.numcontrat} — {c.address or c.contrat_id}"
            for c in self._contracts
        }

        return self.async_show_form(
            step_id="select_contract",
            data_schema=vol.Schema(
                {vol.Required(CONF_CONTRAT_ID): vol.In(options)}
            ),
        )

    async def _create_entry(self, contract: HydropolisContract) -> ConfigFlowResult:
        """Create config entry for the selected contract."""
        await self.async_set_unique_id(contract.contrat_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"Hydropolis {contract.numcontrat}",
            data={
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_CONTRAT_ID: contract.contrat_id,
                "compteur_numserie": contract.compteur_numserie,
            },
        )
