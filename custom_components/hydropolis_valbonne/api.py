from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from .const import (
    HYDROPOLIS_LOGIN_URL,
    HYDROPOLIS_CONSUMPTION_URL,
)

_LOGGER = logging.getLogger(__name__)


class HydropolisValbonneApiError(Exception):
    """Exception raised for API errors."""


class HydropolisValbonneAuthError(HydropolisValbonneApiError):
    """Exception raised for authentication errors."""


class HydropolisValbonneApi:
    """Client for the Hydropolis Valbonne customer portal."""

    def __init__(self, username: str, password: str, session: aiohttp.ClientSession) -> None:
        self._username = username
        self._password = password
        self._session = session

    async def async_login(self) -> None:
        """Log in to the Hydropolis Valbonne customer portal."""
        try:
            get_resp = await self._session.get(HYDROPOLIS_LOGIN_URL)
            get_resp.raise_for_status()
            html = await get_resp.text()
        except aiohttp.ClientError as err:
            raise HydropolisValbonneApiError(f"Cannot reach login page: {err}") from err

        soup = BeautifulSoup(html, "html.parser")
        token_input = soup.find("input", {"name": "_token"})
        token = token_input["value"] if token_input else ""

        payload = {
            "_token": token,
            "username": self._username,
            "password": self._password,
        }

        try:
            post_resp = await self._session.post(
                HYDROPOLIS_LOGIN_URL,
                data=payload,
                allow_redirects=True,
            )
            post_resp.raise_for_status()
            response_html = await post_resp.text()
        except aiohttp.ClientError as err:
            raise HydropolisValbonneApiError(f"Login request failed: {err}") from err

        if "logout" not in response_html.lower() and "déconnexion" not in response_html.lower():
            raise HydropolisValbonneAuthError("Invalid username or password")

    async def async_get_consumption_data(self) -> dict:
        """Fetch consumption data from the portal and return parsed values."""
        try:
            resp = await self._session.get(HYDROPOLIS_CONSUMPTION_URL)
            resp.raise_for_status()
            html = await resp.text()
        except aiohttp.ClientError as err:
            raise HydropolisValbonneApiError(f"Cannot fetch consumption data: {err}") from err

        return self._parse_consumption(html)

    def _parse_consumption(self, html: str) -> dict:
        """Parse the consumption HTML page and return a dict of values."""
        soup = BeautifulSoup(html, "html.parser")
        data: dict = {
            "daily": None,
            "monthly": None,
            "yearly": None,
            "last_index": None,
        }

        def _extract_numeric(text: str | None) -> float | None:
            if text is None:
                return None
            cleaned = text.strip().replace("\xa0", "").replace(",", ".").split()[0]
            try:
                return float(cleaned)
            except (ValueError, IndexError):
                return None

        daily_el = soup.find(class_="daily-consumption") or soup.find(id="daily-consumption")
        if daily_el:
            data["daily"] = _extract_numeric(daily_el.get_text())

        monthly_el = soup.find(class_="monthly-consumption") or soup.find(id="monthly-consumption")
        if monthly_el:
            data["monthly"] = _extract_numeric(monthly_el.get_text())

        yearly_el = soup.find(class_="yearly-consumption") or soup.find(id="yearly-consumption")
        if yearly_el:
            data["yearly"] = _extract_numeric(yearly_el.get_text())

        index_el = soup.find(class_="meter-index") or soup.find(id="meter-index")
        if index_el:
            data["last_index"] = _extract_numeric(index_el.get_text())

        _LOGGER.debug("Parsed consumption data: %s", data)
        return data

    async def async_validate_credentials(self) -> None:
        """Validate credentials by attempting to log in."""
        await self.async_login()
