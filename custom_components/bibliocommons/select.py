"""Select entities for assigning checked-out books to household members."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LIBRARY_NAME, CONF_LIBRARY_SUBDOMAIN, CONF_USERNAME, DOMAIN
from .coordinator import BiblioCommonsCoordinator, LibraryItem

UNASSIGNED = "Unassigned"


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

    known_checkout_ids: set[str] = set()

    def _add_new_entities() -> None:
        if coordinator.data is None:
            return
        new_entities = []
        for item in coordinator.data.checkouts:
            if item.checkout_id not in known_checkout_ids:
                known_checkout_ids.add(item.checkout_id)
                new_entities.append(
                    BookAssignSelect(coordinator, entry, library_name, username, item.checkout_id)
                )
        if new_entities:
            async_add_entities(new_entities)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class BookAssignSelect(CoordinatorEntity[BiblioCommonsCoordinator], SelectEntity):
    """Dropdown to assign a checked-out book to a household member."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:account-heart"

    def __init__(
        self,
        coordinator: BiblioCommonsCoordinator,
        entry: ConfigEntry,
        library_name: str,
        username: str,
        checkout_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._checkout_id = checkout_id
        self._attr_unique_id = f"{entry.entry_id}_assign_{checkout_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"{library_name} – {username}",
            "manufacturer": "BiblioCommons",
            "model": "Library Account",
            "entry_type": "service",
        }

    def _current_item(self) -> LibraryItem | None:
        if self.coordinator.data is None:
            return None
        return next(
            (i for i in self.coordinator.data.checkouts if i.checkout_id == self._checkout_id),
            None,
        )

    @property
    def name(self) -> str:
        item = self._current_item()
        title = item.title if item else f"Book {self._checkout_id}"
        return f"{title} – Assigned To"

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
        if option == UNASSIGNED:
            await self.coordinator.assignment_store.async_unassign(self._checkout_id)
        else:
            await self.coordinator.assignment_store.async_assign(self._checkout_id, option)
        await self.coordinator.async_refresh()
