from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    HunchAuthenticationError,
    HunchClient,
    HunchConnectionError,
    HunchResponseError,
    SnapshotClient,
    normalize_url,
)
from .const import (
    AUTH_AUTO,
    AUTH_BASIC,
    AUTH_DIGEST,
    AUTH_NONE,
    CONF_AREA_THRESHOLD,
    CONF_AUTH_TYPE,
    CONF_CAMERA_NAME,
    CONF_CLEAR_DELAY,
    CONF_DETECTION_INTERVAL,
    CONF_MOTION_ENABLED,
    CONF_MOTION_END_DELAY,
    CONF_PASSWORD,
    CONF_PIXEL_THRESHOLD,
    CONF_POLL_INTERVAL,
    CONF_SERVER_ID,
    CONF_SERVER_URL,
    CONF_SNAPSHOT_URL,
    CONF_THRESHOLD,
    CONF_TOKEN,
    CONF_TRACKING_ENABLED,
    CONF_TRIGGER_FRAMES,
    CONF_USERNAME,
    CONF_VERIFY_TLS,
    CONF_ZONE,
    DEFAULT_AREA_THRESHOLD,
    DEFAULT_CLEAR_DELAY,
    DEFAULT_DETECTION_INTERVAL,
    DEFAULT_MOTION_END_DELAY,
    DEFAULT_PIXEL_THRESHOLD,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_THRESHOLD,
    DEFAULT_TRIGGER_FRAMES,
    DOMAIN,
    SUBENTRY_TYPE_CAMERA,
)
from .image import InvalidImageError, image_dimensions

SERVER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_SERVER_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        probatio.Optional(CONF_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        probatio.Optional(CONF_VERIFY_TLS, default=True): BooleanSelector(),
    }
)

CAMERA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_CAMERA_NAME): TextSelector(),
        probatio.Required(CONF_SNAPSHOT_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        probatio.Optional(CONF_AUTH_TYPE, default=AUTH_AUTO): SelectSelector(
            SelectSelectorConfig(
                options=[AUTH_AUTO, AUTH_BASIC, AUTH_DIGEST, AUTH_NONE],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="auth_type",
            )
        ),
        probatio.Optional(CONF_USERNAME): TextSelector(),
        probatio.Optional(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        probatio.Optional(CONF_VERIFY_TLS, default=True): BooleanSelector(),
        probatio.Optional(CONF_MOTION_ENABLED, default=True): BooleanSelector(),
        probatio.Optional(CONF_TRACKING_ENABLED, default=True): BooleanSelector(),
        probatio.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): NumberSelector(
            NumberSelectorConfig(min=0.5, max=10, step=0.5, mode=NumberSelectorMode.BOX)
        ),
        probatio.Optional(CONF_DETECTION_INTERVAL, default=DEFAULT_DETECTION_INTERVAL): NumberSelector(
            NumberSelectorConfig(min=0.5, max=10, step=0.5, mode=NumberSelectorMode.BOX)
        ),
        probatio.Optional(CONF_THRESHOLD, default=DEFAULT_THRESHOLD): NumberSelector(
            NumberSelectorConfig(min=0.05, max=0.95, step=0.05, mode=NumberSelectorMode.BOX)
        ),
        probatio.Optional(CONF_CLEAR_DELAY, default=DEFAULT_CLEAR_DELAY): NumberSelector(
            NumberSelectorConfig(min=0, max=60, step=1, mode=NumberSelectorMode.BOX)
        ),
        probatio.Optional(CONF_PIXEL_THRESHOLD, default=DEFAULT_PIXEL_THRESHOLD): NumberSelector(
            NumberSelectorConfig(min=5, max=100, step=1, mode=NumberSelectorMode.BOX)
        ),
        probatio.Optional(CONF_AREA_THRESHOLD, default=DEFAULT_AREA_THRESHOLD): NumberSelector(
            NumberSelectorConfig(min=0.001, max=0.5, step=0.001, mode=NumberSelectorMode.BOX)
        ),
        probatio.Optional(CONF_TRIGGER_FRAMES, default=DEFAULT_TRIGGER_FRAMES): NumberSelector(
            NumberSelectorConfig(min=1, max=5, step=1, mode=NumberSelectorMode.BOX)
        ),
        probatio.Optional(CONF_MOTION_END_DELAY, default=DEFAULT_MOTION_END_DELAY): NumberSelector(
            NumberSelectorConfig(min=0, max=30, step=0.5, mode=NumberSelectorMode.BOX)
        ),
    }
)


async def _validate_server(hass, user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_SERVER_URL] = normalize_url(data[CONF_SERVER_URL], server=True)
    status = await HunchClient(async_get_clientsession(hass), data).status()
    data[CONF_SERVER_ID] = str(status["server_id"])
    return data


def _error_key(error: Exception) -> str:
    if isinstance(error, HunchAuthenticationError):
        return "invalid_auth"
    if isinstance(error, (HunchResponseError, InvalidImageError)):
        return "invalid_image" if isinstance(error, InvalidImageError) else "invalid_response"
    if isinstance(error, ValueError):
        return str(error) if str(error) in {"invalid_url", "credentials_in_url"} else "invalid_response"
    return "cannot_connect"


class HunchConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_TYPE_CAMERA: CameraSubentryFlow}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = await _validate_server(self.hass, user_input)
                await self.async_set_unique_id(data[CONF_SERVER_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Hunch ({data[CONF_SERVER_URL]})", data=data)
            except (HunchConnectionError, ValueError) as error:
                errors["base"] = _error_key(error)
        return self.async_show_form(step_id="user", data_schema=SERVER_SCHEMA, errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = dict(user_input)
                if not data.get(CONF_TOKEN):
                    data[CONF_TOKEN] = entry.data.get(CONF_TOKEN, "")
                data = await _validate_server(self.hass, data)
                await self.async_set_unique_id(data[CONF_SERVER_ID])
                self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(entry, data_updates=data)
            except (HunchConnectionError, ValueError) as error:
                errors["base"] = _error_key(error)
        suggested = dict(entry.data)
        suggested[CONF_TOKEN] = ""
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(SERVER_SCHEMA, suggested),
            errors=errors,
        )


class CameraSubentryFlow(ConfigSubentryFlow):
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = await self._validate_camera(user_input)
                return self.async_create_entry(title=data[CONF_CAMERA_NAME], data=data)
            except (HunchConnectionError, ValueError) as error:
                errors["base"] = _error_key(error)
        return self.async_show_form(step_id="user", data_schema=CAMERA_SCHEMA, errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = await self._validate_camera(user_input, dict(subentry.data))
                return self.async_update_and_abort(
                    entry,
                    subentry,
                    title=data[CONF_CAMERA_NAME],
                    data_updates=data,
                )
            except (HunchConnectionError, ValueError) as error:
                errors["base"] = _error_key(error)
        suggested = dict(subentry.data)
        suggested[CONF_PASSWORD] = ""
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(CAMERA_SCHEMA, suggested),
            errors=errors,
        )

    async def _validate_camera(
        self, user_input: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = dict(user_input)
        data[CONF_SNAPSHOT_URL] = normalize_url(data[CONF_SNAPSHOT_URL])
        if existing:
            if not data.get(CONF_PASSWORD):
                data[CONF_PASSWORD] = existing.get(CONF_PASSWORD, "")
            data[CONF_ZONE] = existing.get(CONF_ZONE)
        snapshot = await SnapshotClient(async_get_clientsession(self.hass), data).fetch()
        await self.hass.async_add_executor_job(image_dimensions, snapshot.data)
        return data
