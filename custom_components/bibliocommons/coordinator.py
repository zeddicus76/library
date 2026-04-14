"""Data coordinator for BiblioCommons library integration."""
from __future__ import annotations

import asyncio
import datetime
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    SCAN_INTERVAL_HOURS,
    checkouts_url,
    holds_url,
    login_url,
)

if TYPE_CHECKING:
    from .storage import AssignmentStore

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = datetime.timedelta(hours=SCAN_INTERVAL_HOURS)
OPEN_LIBRARY_COVER = "https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"


@dataclass
class LibraryItem:
    """Represents a checked-out library item."""

    checkout_id: str
    title: str
    subtitle: str | None
    medium: str
    due_date: datetime.date
    isbn: str | None = None
    image_url: str | None = None
    assigned_to: str | None = None
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
    def next_due_item(self) -> LibraryItem | None:
        if not self.checkouts:
            return None
        return min(self.checkouts, key=lambda x: x.due_date)

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


def _extract_image_url(brief: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (isbn, image_url) from a briefInfo dict."""
    isbns: list[str] = brief.get("isbns") or []
    isbn = isbns[0] if isbns else None

    # BiblioCommons may provide a jacket image directly
    jacket = brief.get("jacket") or {}
    image_url: str | None = None
    if isinstance(jacket, dict):
        image_url = jacket.get("small") or jacket.get("medium") or jacket.get("large")

    # Fall back to Open Library cover if we have an ISBN
    if not image_url and isbn:
        image_url = OPEN_LIBRARY_COVER.format(isbn=isbn)

    return isbn, image_url


async def async_fetch_library_name(subdomain: str) -> str:
    """Try to extract the library's display name from its BiblioCommons login page.

    Falls back to a title-cased version of the subdomain if parsing fails.
    """
    url = login_url(subdomain)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params={"destination": "x"}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return subdomain.upper()
                html = await resp.text()

        # BiblioCommons embeds the library name in JS: e.g. "library":{"name":"Kitsap Regional Library"}
        match = re.search(r'"library"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', html)
        if match:
            return match.group(1)

        # Fall back to the page <title>, which is usually "Library Name - Catalog"
        title_match = re.search(r"<title>([^<]+)</title>", html)
        if title_match:
            title = title_match.group(1).split(" - ")[0].strip()
            if title:
                return title
    except Exception:  # noqa: BLE001
        pass

    return subdomain.upper()


class BiblioCommonsClient:
    """Async HTTP client for the BiblioCommons gateway API."""

    def __init__(self, subdomain: str, username: str, password: str) -> None:
        self._subdomain = subdomain
        self._username = username
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._account_id: int | None = None
        self._access_token: str | None = None
        self._session_id: str | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        return self._session

    async def authenticate(self) -> None:
        """Authenticate via the BiblioCommons patron portal."""
        session = await self._get_session()
        url = login_url(self._subdomain)

        # Step 1: Fetch login page to get CSRF token
        async with session.get(url, params={"destination": "x"}) as resp:
            if resp.status != 200:
                raise ConfigEntryAuthFailed(f"Login page returned HTTP {resp.status}")
            html = await resp.text()

        match = re.search(
            r'<input[^>]+name="authenticity_token"[^>]+value="([^"]+)"', html
        )
        if not match:
            raise ConfigEntryAuthFailed(
                "Could not find authenticity_token on login page. "
                "Check that the library subdomain is correct."
            )
        auth_token = match.group(1)

        # Step 2: POST credentials
        async with session.post(
            url,
            data={
                "authenticity_token": auth_token,
                "name": self._username,
                "user_pin": self._password,
            },
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                raise ConfigEntryAuthFailed(f"Login POST returned HTTP {resp.status}")

        # Step 3: Extract session tokens from cookies
        cookies = {c.key: c.value for c in session.cookie_jar}
        access_token = cookies.get("bc_access_token")
        session_id = cookies.get("session_id")

        if not access_token or not session_id:
            raise ConfigEntryAuthFailed(
                "Authentication failed — credentials may be incorrect."
            )

        self._access_token = access_token
        self._session_id = session_id
        self._account_id = int(session_id.split("-")[-1]) + 1
        _LOGGER.debug("Authenticated as account_id=%s", self._account_id)

    def _api_headers(self) -> dict[str, str]:
        return {
            "X-Access-Token": self._access_token or "",
            "X-Session-Id": self._session_id or "",
        }

    async def _get_json(self, url: str) -> dict[str, Any] | None:
        """GET a gateway endpoint, re-authenticating once on 401."""
        if self._account_id is None:
            await self.authenticate()

        session = await self._get_session()
        params = {"accountId": self._account_id}

        async with session.get(url, params=params, headers=self._api_headers()) as resp:
            if resp.status == 401:
                await self.authenticate()
                async with session.get(
                    url,
                    params={"accountId": self._account_id},
                    headers=self._api_headers(),
                ) as retry:
                    if retry.status in (404, 501):
                        return None
                    retry.raise_for_status()
                    return await retry.json()
            if resp.status in (404, 501):
                return None
            resp.raise_for_status()
            return await resp.json()

    async def get_checkouts(self, assignments: dict[str, str]) -> list[LibraryItem]:
        """Fetch current checkouts and merge in household assignments."""
        data = await self._get_json(checkouts_url(self._subdomain))
        return _parse_checkouts(data or {}, assignments)

    async def get_holds(self) -> list[LibraryHold]:
        """Fetch current holds. Returns empty list if endpoint unavailable."""
        try:
            data = await self._get_json(holds_url(self._subdomain))
        except (aiohttp.ClientError, asyncio.TimeoutError):
            _LOGGER.debug("Holds endpoint unavailable for %s", self._subdomain)
            return []
        return _parse_holds(data or {})

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


def _parse_checkouts(
    data: dict[str, Any], assignments: dict[str, str]
) -> list[LibraryItem]:
    items: list[LibraryItem] = []
    entities = data.get("entities", {})
    checkouts = entities.get("checkouts", {})
    bibs = entities.get("bibs", {})

    for checkout in checkouts.values():
        try:
            bib = bibs.get(checkout.get("metadataId"), {})
            brief = bib.get("briefInfo", {})
            due_str = checkout.get("dueDate", "")
            due = datetime.date.fromisoformat(due_str[:10])
            checkout_id = checkout.get("checkoutId", "")
            isbn, image_url = _extract_image_url(brief)
            items.append(
                LibraryItem(
                    checkout_id=checkout_id,
                    title=brief.get("title", "Unknown"),
                    subtitle=brief.get("subtitle"),
                    medium=_translate_medium(brief.get("format", "")),
                    due_date=due,
                    isbn=isbn,
                    image_url=image_url,
                    assigned_to=assignments.get(checkout_id),
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
                datetime.date.fromisoformat(expires_str[:10]) if expires_str else None
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


class BiblioCommonsCoordinator(DataUpdateCoordinator[LibraryData]):
    """Coordinator that polls the BiblioCommons API on a schedule."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: BiblioCommonsClient,
        assignment_store: AssignmentStore,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.assignment_store = assignment_store

    async def _async_update_data(self) -> LibraryData:
        assignments = self.assignment_store.all()
        try:
            checkouts, holds = await asyncio.gather(
                self.client.get_checkouts(assignments),
                self.client.get_holds(),
            )
        except ConfigEntryAuthFailed:
            raise
        except aiohttp.ClientResponseError as exc:
            raise UpdateFailed(f"API error: {exc.status} {exc.message}") from exc
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise UpdateFailed(f"Network error: {exc}") from exc

        # Clean up assignments for returned books
        active_ids = {item.checkout_id for item in checkouts}
        await self.assignment_store.async_cleanup(active_ids)

        return LibraryData(checkouts=checkouts, holds=holds)
