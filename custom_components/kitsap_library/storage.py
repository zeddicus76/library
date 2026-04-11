"""Persistent storage for book-to-person assignments."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "kitsap_library.assignments"


class AssignmentStore:
    """Stores checkout→person assignments in HA's persistent storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}.{entry_id}"
        )
        self._data: dict[str, str] = {}

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        self._data = (stored or {}).get("assignments", {})

    def all(self) -> dict[str, str]:
        return dict(self._data)

    async def async_assign(self, checkout_id: str, person: str) -> None:
        self._data[checkout_id] = person
        await self._store.async_save({"assignments": self._data})

    async def async_unassign(self, checkout_id: str) -> None:
        self._data.pop(checkout_id, None)
        await self._store.async_save({"assignments": self._data})

    async def async_cleanup(self, active_checkout_ids: set[str]) -> None:
        """Remove assignments for books that have been returned."""
        stale = [k for k in self._data if k not in active_checkout_ids]
        if stale:
            for k in stale:
                del self._data[k]
            await self._store.async_save({"assignments": self._data})
