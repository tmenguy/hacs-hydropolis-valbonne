"""Tests for the Hydropolis Valbonne config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hydropolis_valbonne.api import (
    HydropolisApiError,
    HydropolisContract,
)
from custom_components.hydropolis_valbonne.const import CONF_CONTRAT_ID, DOMAIN

from .conftest import FAKE_CONTRAT_ID, FAKE_EMAIL, FAKE_PASSWORD, FAKE_SERIAL


def _make_client_mock(
    authenticate_ok: bool = True,
    contracts: list[HydropolisContract] | None = None,
) -> AsyncMock:
    client = AsyncMock()
    client.authenticate = AsyncMock(return_value=authenticate_ok)
    client.get_contracts = AsyncMock(return_value=contracts or [])
    return client


async def test_show_user_form(hass: HomeAssistant):
    """First call with no input shows the credentials form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_invalid_auth(hass: HomeAssistant):
    client = _make_client_mock(authenticate_ok=False)
    with patch(
        "custom_components.hydropolis_valbonne.config_flow.HydropolisClient",
        return_value=client,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "bad@example.com", CONF_PASSWORD: "wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_connection_error(hass: HomeAssistant):
    client = AsyncMock()
    client.authenticate = AsyncMock(side_effect=HydropolisApiError("timeout"))
    with patch(
        "custom_components.hydropolis_valbonne.config_flow.HydropolisClient",
        return_value=client,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: FAKE_EMAIL, CONF_PASSWORD: FAKE_PASSWORD},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_no_contracts(hass: HomeAssistant):
    client = _make_client_mock(authenticate_ok=True, contracts=[])
    with patch(
        "custom_components.hydropolis_valbonne.config_flow.HydropolisClient",
        return_value=client,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: FAKE_EMAIL, CONF_PASSWORD: FAKE_PASSWORD},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "no_contracts"


async def test_single_contract_creates_entry(
    hass: HomeAssistant, mock_hydropolis_client
):
    """When only one contract exists, entry is created directly."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: FAKE_EMAIL, CONF_PASSWORD: FAKE_PASSWORD},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hydropolis C-9999"
    assert result["data"][CONF_CONTRAT_ID] == FAKE_CONTRAT_ID
    assert result["data"]["compteur_numserie"] == FAKE_SERIAL


async def test_multiple_contracts_shows_select(hass: HomeAssistant):
    """When multiple contracts exist, the select_contract step appears."""
    contracts = [
        HydropolisContract("1001", "C-1001", "P1", "SER1", True, "Addr A"),
        HydropolisContract("1002", "C-1002", "P2", "SER2", True, "Addr B"),
    ]
    client = _make_client_mock(authenticate_ok=True, contracts=contracts)
    with patch(
        "custom_components.hydropolis_valbonne.config_flow.HydropolisClient",
        return_value=client,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: FAKE_EMAIL, CONF_PASSWORD: FAKE_PASSWORD},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_contract"


async def test_select_contract_creates_entry(hass: HomeAssistant):
    contracts = [
        HydropolisContract("1001", "C-1001", "P1", "SER1", True, "Addr A"),
        HydropolisContract("1002", "C-1002", "P2", "SER2", True, "Addr B"),
    ]
    client = _make_client_mock(authenticate_ok=True, contracts=contracts)
    with patch(
        "custom_components.hydropolis_valbonne.config_flow.HydropolisClient",
        return_value=client,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: FAKE_EMAIL, CONF_PASSWORD: FAKE_PASSWORD},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONTRAT_ID: "1002"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONTRAT_ID] == "1002"
    assert result["data"]["compteur_numserie"] == "SER2"


async def test_duplicate_aborts(hass: HomeAssistant, mock_config_entry, mock_hydropolis_client):
    """Adding the same contract a second time aborts."""
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: FAKE_EMAIL, CONF_PASSWORD: FAKE_PASSWORD},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
