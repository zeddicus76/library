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
from .coordinator import KitsapLibraryCoordinator, LibraryData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: KitsapLibraryCoordinator = hass.data[DOMAIN][entry.entry_id]
    username = entry.data[CONF_USERNAME]

    async_add_entities(
        [
            ItemsCheckedOutSensor(coordinator, entry, username),
            NextDueDateSensor(coordinator, entry, username),
            OverdueItemsSensor(coordinator, entry, username),
            HoldsReadySensor(coordinator, entry, username),
            HoldsWaitingSensor(coordinator, entry, username),
        ]
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
    _attr_translation_key = SENSOR_ITEMS_CHECKED_OUT

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
                    "title": item.title,
                    "subtitle": item.subtitle,
                    "medium": item.medium,
                    "due_date": item.due_date.isoformat(),
                    "overdue": item.overdue,
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
    def extra_state_attributes(self) -> dict[str, Any]:
        due = self.data.next_due_date
        if due is None:
            return {}
        days_until = (due - datetime.date.today()).days
        items_due_soon = [
            item.title
            for item in self.data.checkouts
            if item.due_date == due
        ]
        return {
            "days_until_due": days_until,
            "items_due": items_due_soon,
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
                    "title": item.title,
                    "due_date": item.due_date.isoformat(),
                    "days_overdue": (datetime.date.today() - item.due_date).days,
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
