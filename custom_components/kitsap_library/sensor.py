"""Sensor entities for Kitsap Regional Library."""
from __future__ import annotations

import datetime
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_USERNAME,
    DOMAIN,
    SENSOR_HOLDS_READY,
    SENSOR_HOLDS_WAITING,
    SENSOR_ITEMS_CHECKED_OUT,
    SENSOR_NEXT_DUE_DATE,
    SENSOR_OVERDUE_ITEMS,
)
from .coordinator import KitsapLibraryCoordinator, LibraryData, LibraryItem

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: KitsapLibraryCoordinator = hass.data[DOMAIN][entry.entry_id]
    username = entry.data[CONF_USERNAME]

    # Track which per-book sensors exist so we can add/remove dynamically
    known_checkout_ids: set[str] = set()

    summary_sensors = [
        ItemsCheckedOutSensor(coordinator, entry, username),
        NextDueDateSensor(coordinator, entry, username),
        OverdueItemsSensor(coordinator, entry, username),
        HoldsReadySensor(coordinator, entry, username),
        HoldsWaitingSensor(coordinator, entry, username),
    ]
    async_add_entities(summary_sensors)

    def _add_new_book_sensors() -> None:
        if coordinator.data is None:
            return
        new_entities = []
        for item in coordinator.data.checkouts:
            if item.checkout_id not in known_checkout_ids:
                known_checkout_ids.add(item.checkout_id)
                new_entities.append(BookSensor(coordinator, entry, username, item.checkout_id))
        if new_entities:
            async_add_entities(new_entities)

    # Add sensors for books already present at startup
    _add_new_book_sensors()

    # Add sensors for newly checked-out books on each coordinator update
    entry.async_on_unload(
        coordinator.async_add_listener(_add_new_book_sensors)
    )


class KitsapLibrarySensor(CoordinatorEntity[KitsapLibraryCoordinator], SensorEntity):
    """Base class for Kitsap Library sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KitsapLibraryCoordinator,
        entry: ConfigEntry,
        username: str,
        sensor_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._username = username
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"KRL – {username}",
            "manufacturer": "Kitsap Regional Library",
            "model": "BiblioCommons",
            "entry_type": "service",
        }

    @property
    def data(self) -> LibraryData:
        return self.coordinator.data


class ItemsCheckedOutSensor(KitsapLibrarySensor):
    """Number of currently checked-out items."""

    _attr_icon = "mdi:book-open-variant"

    def __init__(self, coordinator, entry, username):
        super().__init__(coordinator, entry, username, SENSOR_ITEMS_CHECKED_OUT)

    @property
    def name(self) -> str:
        return "Items Checked Out"

    @property
    def native_value(self) -> int:
        return self.data.items_checked_out

    @property
    def native_unit_of_measurement(self) -> str:
        return "items"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "checkout_id": item.checkout_id,
                    "title": item.title,
                    "subtitle": item.subtitle,
                    "medium": item.medium,
                    "due_date": item.due_date.isoformat(),
                    "overdue": item.overdue,
                    "assigned_to": item.assigned_to,
                    "image_url": item.image_url,
                }
                for item in self.data.checkouts
            ]
        }


class NextDueDateSensor(KitsapLibrarySensor):
    """Date of the soonest-due item."""

    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = "date"

    def __init__(self, coordinator, entry, username):
        super().__init__(coordinator, entry, username, SENSOR_NEXT_DUE_DATE)

    @property
    def name(self) -> str:
        return "Next Due Date"

    @property
    def native_value(self) -> str | None:
        due = self.data.next_due_date
        return due.isoformat() if due else None

    @property
    def entity_picture(self) -> str | None:
        """Show the cover of the soonest-due item."""
        item = self.data.next_due_item
        return item.image_url if item else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        item = self.data.next_due_item
        if item is None:
            return {}
        days_until = (item.due_date - datetime.date.today()).days
        return {
            "title": item.title,
            "subtitle": item.subtitle,
            "medium": item.medium,
            "checkout_id": item.checkout_id,
            "assigned_to": item.assigned_to,
            "image_url": item.image_url,
            "days_until_due": days_until,
            "items_due": [
                i.title
                for i in self.data.checkouts
                if i.due_date == item.due_date
            ],
        }


class OverdueItemsSensor(KitsapLibrarySensor):
    """Number of overdue items."""

    _attr_icon = "mdi:book-alert"

    def __init__(self, coordinator, entry, username):
        super().__init__(coordinator, entry, username, SENSOR_OVERDUE_ITEMS)

    @property
    def name(self) -> str:
        return "Overdue Items"

    @property
    def native_value(self) -> int:
        return self.data.overdue_items

    @property
    def native_unit_of_measurement(self) -> str:
        return "items"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "checkout_id": item.checkout_id,
                    "title": item.title,
                    "due_date": item.due_date.isoformat(),
                    "days_overdue": (datetime.date.today() - item.due_date).days,
                    "assigned_to": item.assigned_to,
                    "image_url": item.image_url,
                }
                for item in self.data.checkouts
                if item.overdue
            ]
        }


class HoldsReadySensor(KitsapLibrarySensor):
    """Number of holds ready for pickup."""

    _attr_icon = "mdi:package-variant"

    def __init__(self, coordinator, entry, username):
        super().__init__(coordinator, entry, username, SENSOR_HOLDS_READY)

    @property
    def name(self) -> str:
        return "Holds Ready for Pickup"

    @property
    def native_value(self) -> int:
        return self.data.holds_ready

    @property
    def native_unit_of_measurement(self) -> str:
        return "items"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "title": h.title,
                    "pickup_location": h.pickup_location,
                    "expires": h.expires_date.isoformat() if h.expires_date else None,
                }
                for h in self.data.holds
                if h.status == "READY"
            ]
        }


class HoldsWaitingSensor(KitsapLibrarySensor):
    """Number of holds still in the queue."""

    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, entry, username):
        super().__init__(coordinator, entry, username, SENSOR_HOLDS_WAITING)

    @property
    def name(self) -> str:
        return "Holds Waiting"

    @property
    def native_value(self) -> int:
        return self.data.holds_waiting

    @property
    def native_unit_of_measurement(self) -> str:
        return "items"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "items": [
                {"title": h.title, "status": h.status}
                for h in self.data.holds
                if h.status != "READY"
            ]
        }


class BookSensor(KitsapLibrarySensor):
    """One sensor per checked-out book showing cover, due date, and assignment.

    The sensor becomes unavailable once the book is returned (checkout_id
    disappears from the coordinator data). HA will automatically hide
    unavailable entities after a configurable grace period.
    """

    _attr_icon = "mdi:book"

    def __init__(
        self,
        coordinator: KitsapLibraryCoordinator,
        entry: ConfigEntry,
        username: str,
        checkout_id: str,
    ) -> None:
        super().__init__(coordinator, entry, username, f"book_{checkout_id}")
        self._checkout_id = checkout_id

    def _current_item(self) -> LibraryItem | None:
        if self.coordinator.data is None:
            return None
        for item in self.coordinator.data.checkouts:
            if item.checkout_id == self._checkout_id:
                return item
        return None

    @property
    def name(self) -> str:
        item = self._current_item()
        return item.title if item else f"Book {self._checkout_id}"

    @property
    def available(self) -> bool:
        return self._current_item() is not None

    @property
    def native_value(self) -> str | None:
        item = self._current_item()
        return item.due_date.isoformat() if item else None

    @property
    def device_class(self) -> str:
        return "date"

    @property
    def entity_picture(self) -> str | None:
        item = self._current_item()
        return item.image_url if item else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        item = self._current_item()
        if item is None:
            return {}
        days_until = (item.due_date - datetime.date.today()).days
        return {
            "checkout_id": item.checkout_id,
            "title": item.title,
            "subtitle": item.subtitle,
            "medium": item.medium,
            "due_date": item.due_date.isoformat(),
            "days_until_due": days_until,
            "overdue": item.overdue,
            "assigned_to": item.assigned_to,
            "image_url": item.image_url,
            "isbn": item.isbn,
        }
