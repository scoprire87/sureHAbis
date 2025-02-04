"""Support for Sure PetCare Flaps/Pets binary sensors."""
from __future__ import annotations

from homeassistant.util.dt import now as hass_now
from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepy.entities import SurepyEntity
from surepy.entities.devices import Hub as SureHub, SurepyDevice
from surepy.entities.pet import Pet as SurePet
from surepy.enums import EntityType, Location

# pylint: disable=relative-beyond-top-level
from . import SurePetcareAPI
from .const import DOMAIN, SPC, SURE_MANUFACTURER

PARALLEL_UPDATES = 2


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: Any,
    discovery_info: Any = None,
) -> None:
    """Set up Sure PetCare binary-sensor platform."""
    await async_setup_entry(hass, config, async_add_entities)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: Any
) -> None:
    """Set up config entry Sure Pet Care Flaps sensors."""

    entities: list[SurePetcareBinarySensor] = []

    spc: SurePetcareAPI = hass.data[DOMAIN][SPC]

    for surepy_entity in spc.coordinator.data.values():

        if surepy_entity.type == EntityType.PET:
            entities.append(Pet(spc.coordinator, surepy_entity.id, spc))

        elif surepy_entity.type == EntityType.HUB:
            entities.append(Hub(spc.coordinator, surepy_entity.id, spc))

        elif surepy_entity.type in [EntityType.PET_FLAP, EntityType.CAT_FLAP, EntityType.FEEDER, EntityType.FELAQUA]:
            entities.append(DeviceConnectivity(spc.coordinator, surepy_entity.id, spc))

    async_add_entities(entities)


class SurePetcareBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """A binary sensor implementation for Sure Petcare Entities."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        _id: int,
        spc: SurePetcareAPI,
        device_class: BinarySensorDeviceClass | None,
    ):
        """Initialize a Sure Petcare binary sensor."""
        super().__init__(coordinator)

        self._id: int = _id
        self._spc: SurePetcareAPI = spc

        self._coordinator = coordinator

        self._surepy_entity: SurepyEntity = self._coordinator.data[_id]
        self._state: Any = self._surepy_entity.raw_data().get("status", {})

        type_name = self._surepy_entity.type.name.replace("_", " ").title()

        self._attr_name: str = (
            self._surepy_entity.name
            if self._surepy_entity.name
            else f"Unnamed {type_name}"
        )

        self._attr_available = bool(self._state)

        self._attr_device_class = device_class
        self._attr_name: str = f"{type_name} {self._attr_name}"
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}"

        if self._state:
            self._attr_extra_state_attributes = {**self._surepy_entity.raw_data()}

    @property
    def device_info(self):

        device = {}

        try:

            model = f"{self._surepy_entity.type.name.replace('_', ' ').title()}"
            if serial := self._surepy_entity.raw_data().get("serial_number"):
                model = f"{model} ({serial})"
            elif mac_address := self._surepy_entity.raw_data().get("mac_address"):
                model = f"{model} ({mac_address})"
            elif tag_id := self._surepy_entity.raw_data().get("tag_id"):
                model = f"{model} ({tag_id})"

            device = {
                "identifiers": {(DOMAIN, self._id)},
                "name": self._surepy_entity.name.capitalize(),
                "manufacturer": SURE_MANUFACTURER,
                "model": model,
            }

            if self._state:
                versions = self._state.get("version", {})

                if dev_fw_version := versions.get("device", {}).get("firmware"):
                    device["sw_version"] = dev_fw_version

                if (lcd_version := versions.get("lcd", {})) and (
                    rf_version := versions.get("rf", {})
                ):
                    device["sw_version"] = (
                        f"lcd: {
