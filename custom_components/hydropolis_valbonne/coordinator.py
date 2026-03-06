from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HydropolisValbonneApi, HydropolisValbonneApiError
from .const import DOMAIN, UPDATE_INTERVAL_HOURS

_LOGGER = logging.getLogger(__name__)


class HydropolisValbonneCoordinator(DataUpdateCoordinator):
    """Coordinator to manage data fetching from the Hydropolis Valbonne portal."""

    def __init__(self, hass: HomeAssistant, api: HydropolisValbonneApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=UPDATE_INTERVAL_HOURS),
        )
        self.api = api

    async def _async_update_data(self) -> dict:
        """Fetch latest consumption data from the portal."""
        try:
            await self.api.async_login()
            return await self.api.async_get_consumption_data()
        except HydropolisValbonneApiError as err:
            raise UpdateFailed(f"Error fetching Hydropolis Valbonne data: {err}") from err
