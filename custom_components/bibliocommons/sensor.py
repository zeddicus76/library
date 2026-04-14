"""Sensor entities for the BiblioCommons Library integration."""
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
    CONF_LIBRARY_NAME,
    CONF_LIBRARY_SUBDOMAIN,
    CONF_USERNAME,
    DOMAIN,
    SENSOR_HOLDS_READY,
    SENSOR_HOLDS_WAITING,
    SENSOR_ITEMS_CHECKED_OUT,
    SENSOR_NEXT_DUE_DATE,
    SENSOR_OVERDUE_ITEMS,
)
from .coordinator import BiblioCommonsCoordinator, LibraryData, LibraryItem

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BiblioCommonsCoordinator = hass.data[DOMAIN][entry.entry_id]
    library_name = entry.data.get(CONF_LIBRARY_NAME, entry.data[CONF_LIBRARY_SUBDOMAIN].upper())
    username = entry.data[CONF_USERNAME]

    known_checkout_ids: set[str] = set()

    async_add_entities([
        ItemsCheckedOutSensor(coordinator, entry, library_name, username),
        NextDueDateSensor(coordinator, entry, library_name, username),
        OverdueItemsSensor(coordinator, entry, library_name, username),
        HoldsReadySensor(coordinator, entry, library_name, username),
        HoldsWaitingSensor(coordinator, entry, library_name, username),
    ])

    def _add_new_book_sensors() -> None:
        if coordinator.data is None:
            return
        new_entities = []
        for item in coordinator.data.checkouts:
            if item.checkout_id not in known_checkout_ids:
                known_checkout_ids.add(item.checkout_id)
                new_entities.append(
                    BookSensor(coordinator, entry, library_name, username, item.checkout_id)
                )
        if new_entities:
            async_add_entities(new_entities)

    _add_new_book_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_book_sensors))


class BiblioCommonsSensor(CoordinatorEntity[BiblioCommonsCoordinator], SensorEntity):
    """Base class for BiblioCommons sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BiblioCommonsCoordinator,
        entry: ConfigEntry,
        library_name: str,
        username: str,
        sensor_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._username = username
        self._library_name = library_name
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"{library_name} – {username}",
            "manufacturer": "BiblioCommons",
            "model": "Library Account",
            "entry_type": "service",
        }

    @property
    def data(self) -> LibraryData:
        return self.coordinator.data


class ItemsCheckedOutSensor(BiblioCommonsSensor):
    _attr_icon = "mdi:book-open-variant"

    def __init__(self, coordinator, entry, library_name, username):
        super().__init__(coordinator, entry, library_name, username, SENSOR_ITEMS_CHECKED_OUT)

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


class NextDueDateSensor(BiblioCommonsSensor):
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = "date"

    def __init__(self, coordinator, entry, library_name, username):
        super().__init__(coordinator, entry, library_name, username, SENSOR_NEXT_DUE_DATE)

    @property
    def name(self) -> str:
        return "Next Due Date"

    @property
    def native_value(self) -> str | None:
        due = self.data.next_due_date
        return due.isoformat() if due else None

    @property
    def entity_picture(self) -> str | None:
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
            "items_due": [i.title for i in self.data.checkouts if i.due_date == item.due_date],
        }


class OverdueItemsSensor(BiblioCommonsSensor):
    _attr_icon = "mdi:book-alert"

    def __init__(self, coordinator, entry, library_name, username):
        super().__init__(coordinator, entry, library_name, username, SENSOR_OVERDUE_ITEMS)

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


class HoldsReadySensor(BiblioCommonsSensor):
    _attr_icon = "mdi:package-variant"

    def __init__(self, coordinator, entry, library_name, username):
        super().__init__(coordinator, entry, library_name, username, SENSOR_HOLDS_READY)

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


class HoldsWaitingSensor(BiblioCommonsSensor):
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, entry, library_name, username):
        super().__init__(coordinator, entry, library_name, username, SENSOR_HOLDS_WAITING)

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


class BookSensor(BiblioCommonsSensor):
    """One sensor per checked-out book — shows cover, due date, and assignment.

    Becomes unavailable when the book is returned.
    """

    _attr_icon = "mdi:book"

    def __init__(
        self,
        coordinator: BiblioCommonsCoordinator,
        entry: ConfigEntry,
        library_name: str,
        username: str,
        checkout_id: str,
    ) -> None:
        super().__init__(coordinator, entry, library_name, username, f"book_{checkout_id}")
        self._checkout_id = checkout_id

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
