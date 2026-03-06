"""The Hydropolis Valbonne integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import HydropolisConfigEntry, HydropolisCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: HydropolisConfigEntry) -> bool:
    """Set up Hydropolis Valbonne from a config entry."""
    coordinator = HydropolisCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The first refresh ran before sensor entity registration, so statistics
    # import was deferred.  Now the entity exists in the registry; trigger a
    # second refresh so historical data gets imported immediately.
    await coordinator.async_request_refresh()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: HydropolisConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
