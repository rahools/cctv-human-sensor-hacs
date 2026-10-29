from __future__ import annotations

import base64
from typing import Any

import probatio
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import CONF_ZONE, DOMAIN
from .image import image_dimensions


def _entry_and_camera(hass: HomeAssistant, message: dict[str, Any]):
    entry = hass.config_entries.async_get_entry(message["entry_id"])
    if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
        raise ValueError("Camera is not loaded")
    subentry = entry.subentries.get(message["subentry_id"])
    if subentry is None:
        raise ValueError("Camera was not found")
    camera = entry.runtime_data.cameras.get(subentry.subentry_id)
    if camera is None:
        raise ValueError("Camera is not running")
    return entry, subentry, camera


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, websocket_list)
    websocket_api.async_register_command(hass, websocket_frame)
    websocket_api.async_register_command(hass, websocket_save_zone)


@websocket_api.require_admin
@websocket_api.websocket_command({probatio.Required("type"): "hunch/cameras/list"})
@callback
def websocket_list(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    cameras = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if not hasattr(entry, "runtime_data"):
            continue
        for subentry in entry.get_subentries_of_type("camera"):
            runtime = entry.runtime_data.cameras.get(subentry.subentry_id)
            if runtime is None:
                continue
            cameras.append(
                {
                    "entry_id": entry.entry_id,
                    "subentry_id": subentry.subentry_id,
                    "name": subentry.title,
                    "zone": subentry.data.get(CONF_ZONE),
                    "human": runtime.human,
                    "available": runtime.available,
                }
            )
    connection.send_result(msg["id"], {"cameras": cameras})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        probatio.Required("type"): "hunch/cameras/frame",
        probatio.Required("entry_id"): str,
        probatio.Required("subentry_id"): str,
    }
)
@websocket_api.async_response
async def websocket_frame(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    try:
        _, _, camera = _entry_and_camera(hass, msg)
        image = await camera.fetch_preview()
        width, height = await hass.async_add_executor_job(image_dimensions, image)
    except Exception as error:
        connection.send_error(msg["id"], "snapshot_failed", str(error))
        return
    connection.send_result(
        msg["id"],
        {
            "image": base64.b64encode(image).decode("ascii"),
            "content_type": "image/png" if image.startswith(b"\x89PNG") else "image/jpeg",
            "width": width,
            "height": height,
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        probatio.Required("type"): "hunch/cameras/save_zone",
        probatio.Required("entry_id"): str,
        probatio.Required("subentry_id"): str,
        probatio.Required("zone"): probatio.Any(
            None,
            {
                probatio.Required("x"): probatio.Coerce(float),
                probatio.Required("y"): probatio.Coerce(float),
                probatio.Required("width"): probatio.Coerce(float),
                probatio.Required("height"): probatio.Coerce(float),
            },
        ),
    }
)
@callback
def websocket_save_zone(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    try:
        entry, subentry, camera = _entry_and_camera(hass, msg)
        zone = msg["zone"]
        if zone is not None:
            values = [zone[key] for key in ("x", "y", "width", "height")]
            if any(value < 0 or value > 1 for value in values) or zone["width"] < 0.01 or zone["height"] < 0.01:
                raise ValueError("Zone values are outside the image")
            if zone["x"] + zone["width"] > 1.00001 or zone["y"] + zone["height"] > 1.00001:
                raise ValueError("Zone extends beyond the image")
        hass.config_entries.async_update_subentry(entry, subentry, data=dict(subentry.data) | {CONF_ZONE: zone})
        camera.apply_zone(zone)
    except ValueError as error:
        connection.send_error(msg["id"], "invalid_zone", str(error))
        return
    connection.send_result(msg["id"], {"zone": zone})
