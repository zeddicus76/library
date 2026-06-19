"""Select entities for assigning checked-out books to household members.

Uses a fixed number of slot-based entities so that dashboard cards referencing
these entities never break when books are returned and new ones checked out.
Each slot reflects the book at that position in the sorted checkout list.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LIBRARY_NAME, CONF_LIBRARY_SUBDOMAIN, CONF_USERNAME, DOMAIN
from .coordinator import BiblioCommonsCoordinator, LibraryItem

UNASSIGNED = "Unassigned"
MAX_SLOTS = 10


def _person_names(hass: HomeAssistant) -> list[str]:
    """Return sorted display names of all HA person entities."""
    names = []
    for entity_id in hass.states.async_entity_ids("person"):
        state = hass.states.get(entity_id)
        if state:
            name = state.attributes.get("friendly_name") or state.name
            if name:
                names.append(name)
    return sorted(names)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BiblioCommonsCoordinator = hass.data[DOMAIN][entry.entry_id]
    library_name = entry.data.get(CONF_LIBRARY_NAME, entry.data[CONF_LIBRARY_SUBDOMAIN].upper())
    username = entry.data[CONF_USERNAME]

    # Create a fixed set of slot entities upfront. Their entity_ids are stable
    # regardless of which books are currently checked out.
    async_add_entities(
        BookAssignSelect(coordinator, entry, library_name, username, slot_index)
        for slot_index in range(MAX_SLOTS)
    )


class BookAssignSelect(CoordinatorEntity[BiblioCommonsCoordinator], SelectEntity):
    """Dropdown to assign a checked-out book slot to a household member.

    The slot reflects the book at position ``slot_index`` in the coordinator's
    sorted checkout list. When no book occupies the slot the entity is
    unavailable, but its entity_id never changes.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:account-heart"

    def __init__(
        self,
        coordinator: BiblioCommonsCoordinator,
        entry: ConfigEntry,
        library_name: str,
        username: str,
        slot_index: int,
    ) -> None:
        super().__init__(coordinator)
        self._slot_index = slot_index
        # Stable unique_id based on slot position, not checkout_id.
        self._attr_unique_id = f"{entry.entry_id}_assign_slot_{slot_index}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"{library_name} – {username}",
            "manufacturer": "BiblioCommons",
            "model": "Library Account",
            "entry_type": "service",
        }

    def _current_item(self) -> LibraryItem | None:
        """Return the book occupying this slot, or None if the slot is empty."""
        if self.coordinator.data is None:
            return None
        checkouts = self.coordinator.data.checkouts
        if self._slot_index < len(checkouts):
            return checkouts[self._slot_index]
        return None

    @property
    def name(self) -> str:
        item = self._current_item()
        if item:
            return f"{item.title} – Assigned To"
        return f"Book Slot {self._slot_index + 1} – Assigned To"

    @property
    def available(self) -> bool:
        return self._current_item() is not None

    @property
    def options(self) -> list[str]:
        return [UNASSIGNED] + _person_names(self.hass)

    @property
    def current_option(self) -> str:
        item = self._current_item()
        if item and item.assigned_to:
            return item.assigned_to
        return UNASSIGNED

    async def async_select_option(self, option: str) -> None:
        item = self._current_item()
        if item is None:
            return
        if option == UNASSIGNED:
            await self.coordinator.assignment_store.async_unassign(item.checkout_id)
        else:
            await self.coordinator.assignment_store.async_assign(item.checkout_id, option)
        await self.coordinator.async_refresh()
