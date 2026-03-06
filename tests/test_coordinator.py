"""Tests for the Hydropolis Valbonne coordinator."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.hydropolis_valbonne.api import HydropolisApiError
from custom_components.hydropolis_valbonne.const import DOMAIN
from custom_components.hydropolis_valbonne.coordinator import HydropolisCoordinator

from .conftest import FAKE_CONTRAT_ID, _make_measures


async def _setup(hass: HomeAssistant, mock_config_entry):
    """Set up the integration via the HA config entry machinery."""
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator: HydropolisCoordinator = mock_config_entry.runtime_data
    return coordinator


async def test_first_refresh_fetches_full_history(
    hass: HomeAssistant,
    mock_config_entry,
    mock_hydropolis_client,
):
    """On the very first run, data_available_since is used as start date."""
    coordinator = await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert coordinator.data is not None
    assert coordinator.data.meter_total_liters > 0
    assert coordinator.data.last_measurement is not None
    mock_hydropolis_client.get_daily_measures.assert_called()


async def test_no_measures_first_run_raises(
    hass: HomeAssistant,
    mock_config_entry,
    mock_hydropolis_client,
):
    """If no measures come back on the first refresh, entry fails to load."""
    mock_hydropolis_client.get_daily_measures = AsyncMock(return_value=[])

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_no_new_measures_keeps_previous(
    hass: HomeAssistant,
    mock_config_entry,
    mock_hydropolis_client,
):
    """When subsequent refresh returns no new data, previous data is kept."""
    coordinator = await _setup(hass, mock_config_entry)
    prev_data = coordinator.data

    mock_hydropolis_client.get_daily_measures = AsyncMock(return_value=[])
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data is prev_data


async def test_api_error_raises_update_failed(
    hass: HomeAssistant,
    mock_config_entry,
    mock_hydropolis_client,
):
    coordinator = await _setup(hass, mock_config_entry)

    mock_hydropolis_client.get_daily_measures = AsyncMock(
        side_effect=HydropolisApiError("server down")
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False


async def test_statistic_id_matches_entity_id(
    hass: HomeAssistant,
    mock_config_entry,
    mock_hydropolis_client,
):
    """Verify that sensor_statistic_id uses the entity registry, not DOMAIN."""
    coordinator = await _setup(hass, mock_config_entry)

    stat_id = coordinator.sensor_statistic_id
    assert stat_id is not None
    assert DOMAIN not in stat_id.replace("sensor.", ""), (
        f"statistic_id should NOT contain the domain name: {stat_id}"
    )
    assert FAKE_CONTRAT_ID in stat_id
    assert stat_id.startswith("sensor.")


async def test_incremental_refresh(
    hass: HomeAssistant,
    mock_config_entry,
    mock_hydropolis_client,
):
    """After initial import, second refresh should still work with new data."""
    coordinator = await _setup(hass, mock_config_entry)

    new_measures = _make_measures(count=1, start_date=date.today())
    mock_hydropolis_client.get_daily_measures = AsyncMock(return_value=new_measures)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data is not None
    assert coordinator.data.meter_total_liters == new_measures[-1].meter_index
