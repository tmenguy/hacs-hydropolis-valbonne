"""Data update coordinator for Hydropolis Valbonne."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    StatisticMeanType,
    StatisticsRow,
    async_import_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util
from homeassistant.util.unit_conversion import VolumeConverter

from .api import DailyMeasure, HydropolisApiError, HydropolisAuthError, HydropolisClient
from .const import CONF_CONTRAT_ID, DATA_REFRESH_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

FALLBACK_HISTORY_DAYS = 365 * 4


@dataclass
class HydropolisData:
    """Latest meter reading from the API."""

    meter_total_liters: int
    last_measurement: datetime


type HydropolisConfigEntry = ConfigEntry[HydropolisCoordinator]


class HydropolisCoordinator(DataUpdateCoordinator[HydropolisData]):
    """Coordinator that fetches water meter readings from Hydropolis.

    Each refresh is incremental: it checks the last recorded statistic in the
    HA database and only fetches data from the API starting after that date.
    On the very first run (no statistics yet), it pulls all available history
    back to the contract start date.
    """

    _client: HydropolisClient
    config_entry: HydropolisConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: HydropolisConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DATA_REFRESH_INTERVAL,
            always_update=True,
            config_entry=config_entry,
        )
        self._contrat_id: str = config_entry.data[CONF_CONTRAT_ID]
        self._serial: str = config_entry.data["compteur_numserie"]

    @property
    def _sensor_unique_id(self) -> str:
        """The unique_id we assign to the water meter sensor entity."""
        return f"{self._contrat_id}_water_meter"

    @property
    def sensor_statistic_id(self) -> str | None:
        """Look up the real entity_id from the entity registry.

        Returns None if the sensor entity has not been registered yet
        (e.g. during the very first coordinator refresh, before platform setup).
        """
        registry = er.async_get(self.hass)
        return registry.async_get_entity_id("sensor", DOMAIN, self._sensor_unique_id)

    async def _async_setup(self) -> None:
        session = async_get_clientsession(self.hass)
        self._client = HydropolisClient(
            session,
            self.config_entry.data[CONF_USERNAME],
            self.config_entry.data[CONF_PASSWORD],
        )
        if not await self._client.authenticate():
            raise ConfigEntryError("Invalid credentials for Hydropolis")

    async def _async_update_data(self) -> HydropolisData:
        """Incremental fetch: get data from last known stat to today.

        First run pulls full history; subsequent runs only the gap.
        Also imports all fetched data into HA long-term statistics so
        the Energy dashboard has complete history.
        """
        today = dt_util.now().date()

        last_stat = await self._get_last_stat()
        if last_stat is not None:
            last_recorded = datetime.fromtimestamp(last_stat["start"]).date()
            start = last_recorded + timedelta(days=1)
            _LOGGER.debug(
                "Incremental fetch from %s (last stat: %s)", start, last_recorded
            )
        else:
            start = self._client.data_available_since
            if start is None:
                start = today - timedelta(days=FALLBACK_HISTORY_DAYS)
            _LOGGER.info("First fetch — pulling history from %s", start)

        try:
            measures = await self._client.get_daily_measures(
                self._contrat_id, self._serial, start, today
            )
        except (HydropolisApiError, HydropolisAuthError) as err:
            raise UpdateFailed(f"Error fetching Hydropolis data: {err}") from err

        if not measures:
            if self.data is not None:
                _LOGGER.debug("No new measures, keeping previous reading")
                return self.data
            raise UpdateFailed("No measures returned from Hydropolis API")

        self._import_statistics(measures)

        latest = measures[-1]
        _LOGGER.debug(
            "Hydropolis meter: %d L at %s (%d measures fetched)",
            latest.meter_index,
            latest.timestamp.isoformat(),
            len(measures),
        )

        return HydropolisData(
            meter_total_liters=latest.meter_index,
            last_measurement=latest.timestamp,
        )

    def _import_statistics(self, measures: list[DailyMeasure]) -> None:
        """Push fetched daily measures into HA long-term statistics."""
        statistic_id = self.sensor_statistic_id
        if statistic_id is None:
            _LOGGER.debug(
                "Sensor entity not yet registered, deferring statistics import"
            )
            return

        statistics: list[StatisticData] = []
        for measure in measures:
            if measure.consumption_liters < 0:
                continue
            statistics.append(
                StatisticData(
                    start=dt_util.start_of_local_day(measure.date),
                    state=float(measure.meter_index),
                    sum=float(measure.meter_index),
                )
            )

        if not statistics:
            return

        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name="Water meter",
            source="recorder",
            statistic_id=statistic_id,
            unit_class=VolumeConverter.UNIT_CLASS,
            unit_of_measurement=UnitOfVolume.LITERS,
        )

        async_import_statistics(self.hass, metadata, statistics)
        _LOGGER.debug("Imported %d statistics entries to %s", len(statistics), statistic_id)

    async def _get_last_stat(self) -> StatisticsRow | None:
        """Find the most recent recorded statistic for this sensor."""
        statistic_id = self.sensor_statistic_id
        if statistic_id is None:
            return None

        from homeassistant.components.recorder import get_instance

        last = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True, {"sum"}
        )
        return last[statistic_id][0] if last else None
