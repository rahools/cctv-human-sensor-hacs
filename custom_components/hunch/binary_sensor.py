from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .camera import CameraRuntime
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry in entry.get_subentries_of_type("camera"):
        runtime = entry.runtime_data.cameras[subentry.subentry_id]
        async_add_entities([HumanSensor(runtime, subentry.title)], config_subentry_id=subentry.subentry_id)


class HumanSensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Human"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_should_poll = False

    def __init__(self, runtime: CameraRuntime, camera_name: str) -> None:
        self.runtime = runtime
        self._attr_unique_id = f"{runtime.subentry_id}_human"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.subentry_id)},
            name=camera_name,
            manufacturer="Hunch",
            model="CCTV human detection",
        )

    @property
    def is_on(self) -> bool | None:
        return self.runtime.human

    @property
    def available(self) -> bool:
        return self.runtime.available

    @property
    def extra_state_attributes(self) -> dict[str, str | float | bool | None]:
        return {
            "confidence": self.runtime.confidence,
            "last_checked": self.runtime.last_checked,
            "last_detected": self.runtime.last_detected,
            "motion_filtering": self.runtime.config.get("motion_enabled", True),
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.runtime.async_listen(self.async_write_ha_state))
