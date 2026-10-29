from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HunchClient, HunchConnectionError, SnapshotClient
from .camera import CameraRuntime
from .const import DOMAIN, PANEL_URL
from .websocket import async_register_websocket_commands


@dataclass(slots=True)
class HunchRuntimeData:
    client: HunchClient
    cameras: dict[str, CameraRuntime]


HunchConfigEntry: TypeAlias = ConfigEntry[HunchRuntimeData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async_register_websocket_commands(hass)
    panel_path = Path(__file__).parent / "frontend" / "hunch-panel.js"
    await hass.http.async_register_static_paths([StaticPathConfig(PANEL_URL, str(panel_path), cache_headers=False)])
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path="hunch",
        webcomponent_name="hunch-panel",
        sidebar_title="Hunch",
        sidebar_icon="mdi:account-search",
        module_url=PANEL_URL,
        require_admin=True,
        config_panel_domain=DOMAIN,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HunchConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = HunchClient(session, dict(entry.data))
    try:
        await client.status()
    except HunchConnectionError as error:
        raise ConfigEntryNotReady("Hunch server is unavailable or not ready") from error

    cameras = {
        subentry.subentry_id: CameraRuntime(
            hass,
            subentry.subentry_id,
            dict(subentry.data),
            SnapshotClient(session, dict(subentry.data)),
            client,
        )
        for subentry in entry.get_subentries_of_type("camera")
    }
    entry.runtime_data = HunchRuntimeData(client, cameras)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.BINARY_SENSOR])
    for camera in cameras.values():
        await camera.async_start()
    return True


async def _async_update_listener(hass: HomeAssistant, entry: HunchConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HunchConfigEntry) -> bool:
    for camera in entry.runtime_data.cameras.values():
        await camera.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, [Platform.BINARY_SENSOR])
