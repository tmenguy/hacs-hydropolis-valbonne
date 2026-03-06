"""API client for Hydropolis Valbonne water utility."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime
import json
import logging

import aiohttp

from .const import (
    OMEGA_API_ID,
    OMEGA_API_URL,
    OMEGA_SSO_URL,
    THREINT_API_ID,
    THREINT_API_URL,
)

_LOGGER = logging.getLogger(__name__)

JSONAPI_CONTENT_TYPE = "application/vnd.api+json"


class HydropolisAuthError(Exception):
    """Raised when authentication fails."""


class HydropolisApiError(Exception):
    """Raised when an API call fails."""


@dataclass
class HydropolisContract:
    """A water contract returned by the Omega API."""

    contrat_id: str
    numcontrat: str
    pconso_id: str
    compteur_numserie: str
    actif: bool
    address: str | None = None


@dataclass
class DailyMeasure:
    """A single daily consumption measure from the 3Int API."""

    date: date
    timestamp: datetime
    consumption_liters: int
    meter_index: int


class HydropolisClient:
    """Async client for the Hydropolis / JVS Omega / 3Int APIs."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password

        self._omega_token: str | None = None
        self._omega_sso_id: str | None = None
        self._omega_app_id: str | None = None

        self._3int_token: str | None = None
        self._data_available_since: date | None = None

    async def authenticate(self) -> bool:
        """Authenticate against the Omega SSO and return True on success."""
        self._omega_token = None
        try:
            resp = await self._session.post(
                f"{OMEGA_SSO_URL}/v1/sso/signin",
                json={"login": self._username, "password": self._password, "remember": False},
                headers={
                    "Content-Type": JSONAPI_CONTENT_TYPE,
                    "Accept": JSONAPI_CONTENT_TYPE,
                },
            )
        except aiohttp.ClientError as err:
            raise HydropolisApiError(f"Connection error during login: {err}") from err

        if resp.status != 201:
            _LOGGER.debug("SSO login returned status %s", resp.status)
            return False

        self._omega_token = resp.headers.get("authorization")
        self._omega_sso_id = resp.headers.get("ssoid")
        self._omega_app_id = resp.headers.get("appid")

        if not self._omega_token:
            _LOGGER.error("SSO login succeeded but no authorization token in response")
            return False

        return True

    def _omega_headers(self) -> dict[str, str]:
        """Build headers for Omega API calls."""
        headers: dict[str, str] = {
            "Content-Type": JSONAPI_CONTENT_TYPE,
            "Accept": JSONAPI_CONTENT_TYPE,
            "ApiId": OMEGA_API_ID,
        }
        if self._omega_token:
            headers["Authorization"] = f"Bearer {self._omega_token}"
        if self._omega_sso_id:
            headers["SsoId"] = self._omega_sso_id
        if self._omega_app_id:
            headers["AppId"] = self._omega_app_id
        return headers

    async def get_contracts(self) -> list[HydropolisContract]:
        """Fetch the list of water contracts for the authenticated user."""
        if not self._omega_token:
            raise HydropolisAuthError("Not authenticated")

        try:
            resp = await self._session.get(
                f"{OMEGA_API_URL}/v1/iclient/contrat?len=0",
                headers=self._omega_headers(),
            )
        except aiohttp.ClientError as err:
            raise HydropolisApiError(f"Error fetching contracts: {err}") from err

        if resp.status != 200:
            raise HydropolisApiError(f"Contracts endpoint returned {resp.status}")

        data = await resp.json(content_type=None)
        contracts: list[HydropolisContract] = []

        included_by_type: dict[str, dict[str, dict]] = {}
        for item in data.get("included", []):
            t = item.get("type", "")
            iid = item.get("id", "")
            included_by_type.setdefault(t, {})[iid] = item.get("attributes", {})

        for contrat in data.get("data", []):
            attrs = contrat.get("attributes", {})
            contrat_id = attrs.get("contrat_id", "")
            pconso_id = attrs.get("pconso_id", "")

            numserie = ""
            compteurs = included_by_type.get("IClient_Compteur", {})
            for compteur_attrs in compteurs.values():
                numserie = compteur_attrs.get("numserie", "")
                if numserie:
                    break

            address = ""
            voies = included_by_type.get("IClient_Voie", {})
            for voie_attrs in voies.values():
                address = voie_attrs.get("libvoie", "")
                if address:
                    break

            contracts.append(
                HydropolisContract(
                    contrat_id=contrat_id,
                    numcontrat=attrs.get("numcontrat", ""),
                    pconso_id=pconso_id,
                    compteur_numserie=numserie,
                    actif=attrs.get("actif") == "1",
                    address=address or None,
                )
            )

        return contracts

    async def _authenticate_3int(self, contrat_id: str, serial: str) -> None:
        """Exchange the Omega token for a 3Int API token."""
        try:
            resp = await self._session.post(
                f"{THREINT_API_URL}/authentication_token",
                json={
                    "jvstoken": self._omega_token,
                    "ApiId": THREINT_API_ID,
                    "serial": serial,
                    "contrat_id": contrat_id,
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        except aiohttp.ClientError as err:
            raise HydropolisApiError(f"3Int auth error: {err}") from err

        if resp.status != 200:
            raise HydropolisApiError(f"3Int auth returned {resp.status}")

        body = await resp.json()
        self._3int_token = body.get("token")
        if not self._3int_token:
            raise HydropolisApiError("3Int auth succeeded but no token returned")

        try:
            payload = self._3int_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            datedeb_str = claims.get("datedeb", "")
            if datedeb_str:
                self._data_available_since = datetime.fromisoformat(
                    datedeb_str.strip()
                ).date()
        except (IndexError, ValueError, TypeError):
            _LOGGER.debug("Could not parse datedeb from 3Int JWT")

    async def get_daily_measures(
        self,
        contrat_id: str,
        serial: str,
        start: date,
        end: date,
    ) -> list[DailyMeasure]:
        """Fetch daily consumption measures for a date range.

        The 3Int API paginates at ~365 items per page. This method iterates
        through all pages so callers always receive the complete result set.
        Handles full re-authentication if needed (Omega SSO + 3Int token).
        """
        if not self._omega_token:
            if not await self.authenticate():
                raise HydropolisAuthError("Failed to authenticate with Omega SSO")

        if not self._3int_token:
            await self._authenticate_3int(contrat_id, serial)

        start_str = start.strftime("%Y-%m-%d") + "T00:00:00"
        end_str = end.strftime("%Y-%m-%d") + "T23:59:59"

        base_url = (
            f"{THREINT_API_URL}/measures"
            f"?dateStatement[after]={start_str}"
            f"&dateStatement[before]={end_str}"
            f"&order[dateStatement]=asc"
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._3int_token}",
        }

        measures: list[DailyMeasure] = []
        page = 1

        while True:
            url = f"{base_url}&page={page}"

            try:
                resp = await self._session.get(url, headers=headers)
            except aiohttp.ClientError as err:
                raise HydropolisApiError(f"Measures fetch error: {err}") from err

            if resp.status == 401:
                _LOGGER.debug("3Int token expired, re-authenticating")
                self._3int_token = None
                self._omega_token = None
                return await self.get_daily_measures(contrat_id, serial, start, end)

            if resp.status != 200:
                raise HydropolisApiError(f"Measures endpoint returned {resp.status}")

            raw = await resp.json()
            if not raw:
                break

            for item in raw:
                try:
                    dt_str = item["dateStatement"]
                    dt = datetime.fromisoformat(dt_str)
                    consumption = int(item.get("consumption", 0))
                    last_index = item.get("lastIndex", {})
                    meter_value = int(last_index.get("Value", 0))

                    measures.append(
                        DailyMeasure(
                            date=dt.date(),
                            timestamp=dt,
                            consumption_liters=consumption,
                            meter_index=meter_value,
                        )
                    )
                except (KeyError, ValueError, TypeError) as err:
                    _LOGGER.debug("Skipping malformed measure: %s", err)
                    continue

            _LOGGER.debug("Page %d: %d items fetched", page, len(raw))
            page += 1

        return measures

    @property
    def data_available_since(self) -> date | None:
        """Earliest date with data, extracted from the 3Int JWT."""
        return self._data_available_since

    def invalidate_tokens(self) -> None:
        """Clear cached tokens, forcing re-authentication on next call."""
        self._omega_token = None
        self._3int_token = None
