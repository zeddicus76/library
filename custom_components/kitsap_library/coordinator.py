"""Data coordinator for Kitsap Regional Library."""
from __future__ import annotations

import asyncio
import datetime
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CHECKOUTS_URL,
    DOMAIN,
    HOLDS_URL,
    LOGIN_URL,
    SCAN_INTERVAL_HOURS,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = datetime.timedelta(hours=SCAN_INTERVAL_HOURS)


@dataclass
class LibraryItem:
    """Represents a checked-out library item."""

    checkout_id: str
    title: str
    subtitle: str | None
    medium: str
    due_date: datetime.date
    overdue: bool = field(init=False)

    def __post_init__(self) -> None:
        self.overdue = self.due_date < datetime.date.today()


@dataclass
class LibraryHold:
    """Represents a library hold."""

    hold_id: str
    title: str
    status: str  # "READY" or "NOT_YET_AVAILABLE" etc.
    pickup_location: str | None = None
    expires_date: datetime.date | None = None


@dataclass
class LibraryData:
    """Aggregated library account data."""

    checkouts: list[LibraryItem] = field(default_factory=list)
    holds: list[LibraryHold] = field(default_factory=list)

    @property
    def items_checked_out(self) -> int:
        return len(self.checkouts)

    @property
    def overdue_items(self) -> int:
        return sum(1 for item in self.checkouts if item.overdue)

    @property
    def next_due_date(self) -> datetime.date | None:
        if not self.checkouts:
            return None
        return min(item.due_date for item in self.checkouts)

    @property
    def holds_ready(self) -> int:
        return sum(1 for h in self.holds if h.status == "READY")

    @property
    def holds_waiting(self) -> int:
        return sum(1 for h in self.holds if h.status != "READY")


def _translate_medium(medium: str) -> str:
    return {
        "BK": "book",
        "EAUDIOBOOK": "e-audiobook",
        "EBOOK": "e-book",
        "GRAPHIC_NOVEL": "graphic novel",
        "DVD": "dvd",
        "MUSIC_CD": "music cd",
        "MAGAZINE": "magazine",
    }.get(medium, medium.lower().replace("_", " "))


class KitsapLibraryClient:
    """Async HTTP client for the BiblioCommons API."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._account_id: int | None = None
        self._access_token: str | None = None
        self._session_id: str | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            jar = aiohttp.CookieJar()
            self._session = aiohttp.ClientSession(cookie_jar=jar)
        return self._session

    async def authenticate(self) -> None:
        """Authenticate with Kitsap Regional Library BiblioCommons portal."""
        session = await self._get_session()

        # Step 1: Get the login page and extract the CSRF token
        async with session.get(
            LOGIN_URL, params={"destination": "x"}
        ) as resp:
            if resp.status != 200:
                raise ConfigEntryAuthFailed(
                    f"Login page returned HTTP {resp.status}"
                )
            html = await resp.text()

        match = re.search(
            r'<input[^>]+name="authenticity_token"[^>]+value="([^"]+)"', html
        )
        if not match:
            raise ConfigEntryAuthFailed(
                "Could not find authenticity_token on login page"
            )
        auth_token = match.group(1)

        # Step 2: POST credentials
        data = {
            "authenticity_token": auth_token,
            "name": self._username,
            "user_pin": self._password,
        }
        async with session.post(
            LOGIN_URL, data=data, allow_redirects=True
        ) as resp:
            if resp.status != 200:
                raise ConfigEntryAuthFailed(
                    f"Login POST returned HTTP {resp.status}"
                )

        # Step 3: Extract tokens from cookies
        cookies = {c.key: c.value for c in session.cookie_jar}
        access_token = cookies.get("bc_access_token")
        session_id = cookies.get("session_id")

        if not access_token or not session_id:
            raise ConfigEntryAuthFailed(
                "Authentication failed: credentials may be incorrect"
            )

        self._access_token = access_token
        self._session_id = session_id
        # Account ID is derived from the session ID per BiblioCommons convention
        self._account_id = int(session_id.split("-")[-1]) + 1

        _LOGGER.debug("Authenticated as account_id=%s", self._account_id)

    def _api_headers(self) -> dict[str, str]:
        return {
            "X-Access-Token": self._access_token or "",
            "X-Session-Id": self._session_id or "",
        }

    async def get_checkouts(self) -> list[LibraryItem]:
        """Fetch current checkouts."""
        if self._account_id is None:
            await self.authenticate()

        session = await self._get_session()
        params = {"accountId": self._account_id}

        async with session.get(
            CHECKOUTS_URL, params=params, headers=self._api_headers()
        ) as resp:
            if resp.status == 401:
                # Token expired — re-authenticate once
                await self.authenticate()
                async with session.get(
                    CHECKOUTS_URL, params={"accountId": self._account_id},
                    headers=self._api_headers()
                ) as retry:
                    retry.raise_for_status()
                    data = await retry.json()
            else:
                resp.raise_for_status()
                data = await resp.json()

        return _parse_checkouts(data)

    async def get_holds(self) -> list[LibraryHold]:
        """Fetch current holds. Returns empty list if endpoint unavailable."""
        if self._account_id is None:
            await self.authenticate()

        session = await self._get_session()
        params = {"accountId": self._account_id}

        try:
            async with session.get(
                HOLDS_URL, params=params, headers=self._api_headers()
            ) as resp:
                if resp.status in (404, 501):
                    return []
                if resp.status == 401:
                    await self.authenticate()
                    async with session.get(
                        HOLDS_URL, params={"accountId": self._account_id},
                        headers=self._api_headers()
                    ) as retry:
                        if retry.status in (404, 501):
                            return []
                        retry.raise_for_status()
                        data = await retry.json()
                else:
                    resp.raise_for_status()
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            _LOGGER.debug("Holds endpoint unavailable")
            return []

        return _parse_holds(data)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


def _parse_checkouts(data: dict[str, Any]) -> list[LibraryItem]:
    items: list[LibraryItem] = []
    entities = data.get("entities", {})
    checkouts = entities.get("checkouts", {})
    bibs = entities.get("bibs", {})

    for checkout in checkouts.values():
        try:
            bib = bibs.get(checkout.get("metadataId"), {})
            brief = bib.get("briefInfo", {})
            due_str = checkout.get("dueDate", "")
            due = datetime.date.fromisoformat(due_str[:10])  # handle datetime strings
            items.append(
                LibraryItem(
                    checkout_id=checkout.get("checkoutId", ""),
                    title=brief.get("title", "Unknown"),
                    subtitle=brief.get("subtitle"),
                    medium=_translate_medium(brief.get("format", "")),
                    due_date=due,
                )
            )
        except (KeyError, ValueError) as exc:
            _LOGGER.warning("Could not parse checkout entry: %s", exc)

    return sorted(items, key=lambda x: x.due_date)


def _parse_holds(data: dict[str, Any]) -> list[LibraryHold]:
    holds: list[LibraryHold] = []
    entities = data.get("entities", {})
    holds_data = entities.get("holds", {})
    bibs = entities.get("bibs", {})

    for hold in holds_data.values():
        try:
            bib = bibs.get(hold.get("metadataId"), {})
            brief = bib.get("briefInfo", {})
            status = hold.get("status", "UNKNOWN")
            expires_str = hold.get("expiryDate") or hold.get("pickupByDate")
            expires = (
                datetime.date.fromisoformat(expires_str[:10])
                if expires_str
                else None
            )
            holds.append(
                LibraryHold(
                    hold_id=hold.get("holdId", ""),
                    title=brief.get("title", "Unknown"),
                    status=status,
                    pickup_location=hold.get("pickupLocation", {}).get("name"),
                    expires_date=expires,
                )
            )
        except (KeyError, ValueError) as exc:
            _LOGGER.warning("Could not parse hold entry: %s", exc)

    return holds


class KitsapLibraryCoordinator(DataUpdateCoordinator[LibraryData]):
    """Coordinator that polls the library API on a schedule."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: KitsapLibraryClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> LibraryData:
        try:
            checkouts, holds = await asyncio.gather(
                self.client.get_checkouts(),
                self.client.get_holds(),
            )
        except ConfigEntryAuthFailed:
            raise
        except aiohttp.ClientResponseError as exc:
            raise UpdateFailed(f"API error: {exc.status} {exc.message}") from exc
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise UpdateFailed(f"Network error: {exc}") from exc

        return LibraryData(checkouts=checkouts, holds=holds)
