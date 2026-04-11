"""Kitsap Regional Library integration for Home Assistant."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN
from .coordinator import KitsapLibraryClient, KitsapLibraryCoordinator
from .storage import AssignmentStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

SERVICE_ASSIGN_ITEM = "assign_item"
SERVICE_UNASSIGN_ITEM = "unassign_item"

SERVICE_ASSIGN_SCHEMA = vol.Schema(
    {
        vol.Required("checkout_id"): cv.string,
        vol.Required("person"): cv.string,
    }
)

SERVICE_UNASSIGN_SCHEMA = vol.Schema(
    {
        vol.Required("checkout_id"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kitsap Regional Library from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    assignment_store = AssignmentStore(hass, entry.entry_id)
    await assignment_store.async_load()

    client = KitsapLibraryClient(username, password)
    try:
        await client.authenticate()
    except Exception as exc:
        await client.close()
        raise ConfigEntryNotReady(f"Unable to authenticate: {exc}") from exc

    coordinator = KitsapLibraryCoordinator(hass, client, assignment_store)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unloaded:
        coordinator: KitsapLibraryCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.close()

    # Unregister services when the last entry is removed
    if not hass.data.get(DOMAIN):
        for service in (SERVICE_ASSIGN_ITEM, SERVICE_UNASSIGN_ITEM):
            hass.services.async_remove(DOMAIN, service)

    return unloaded


def _async_register_services(hass: HomeAssistant) -> None:
    """Register assign/unassign services (idempotent — safe to call multiple times)."""

    if hass.services.has_service(DOMAIN, SERVICE_ASSIGN_ITEM):
        return

    async def _handle_assign(call: ServiceCall) -> None:
        checkout_id: str = call.data["checkout_id"]
        person: str = call.data["person"]

        coordinator = _get_coordinator(hass, checkout_id)
        await coordinator.assignment_store.async_assign(checkout_id, person)
        await coordinator.async_refresh()

    async def _handle_unassign(call: ServiceCall) -> None:
        checkout_id: str = call.data["checkout_id"]

        coordinator = _get_coordinator(hass, checkout_id)
        await coordinator.assignment_store.async_unassign(checkout_id)
        await coordinator.async_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_ASSIGN_ITEM, _handle_assign, schema=SERVICE_ASSIGN_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UNASSIGN_ITEM, _handle_unassign, schema=SERVICE_UNASSIGN_SCHEMA
    )


def _get_coordinator(
    hass: HomeAssistant, checkout_id: str
) -> KitsapLibraryCoordinator:
    """Find the coordinator that owns the given checkout_id."""
    coordinators: dict[str, KitsapLibraryCoordinator] = hass.data.get(DOMAIN, {})
    for coordinator in coordinators.values():
        if coordinator.data and any(
            item.checkout_id == checkout_id for item in coordinator.data.checkouts
        ):
            return coordinator
    # Fall back to the first (and usually only) coordinator
    if coordinators:
        return next(iter(coordinators.values()))
    raise ServiceValidationError("No Kitsap Library account configured")
