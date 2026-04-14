"""Config flow for the BiblioCommons Library integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import (
    CONF_LIBRARY_NAME,
    CONF_LIBRARY_SUBDOMAIN,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from .coordinator import BiblioCommonsClient, async_fetch_library_name

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LIBRARY_SUBDOMAIN): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class BiblioCommonsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            subdomain = user_input[CONF_LIBRARY_SUBDOMAIN].strip().lower()
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]

            # Unique ID: subdomain + username so multiple accounts/libraries can coexist
            await self.async_set_unique_id(f"{subdomain}_{username.lower()}")
            self._abort_if_unique_id_configured()

            client = BiblioCommonsClient(subdomain, username, password)
            try:
                await client.authenticate()
            except ConfigEntryAuthFailed:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during authentication")
                errors["base"] = "unknown"
            else:
                library_name = await async_fetch_library_name(subdomain)
                await client.close()
                return self.async_create_entry(
                    title=f"{library_name} – {username}",
                    data={
                        CONF_LIBRARY_SUBDOMAIN: subdomain,
                        CONF_LIBRARY_NAME: library_name,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )
            finally:
                await client.close()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "libraries_url": "https://www.bibliocommons.com/libraries-we-work-with"
            },
        )
