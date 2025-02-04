"""Support for Sure PetCare Flaps/Pets binary sensors."""
from __future__ import annotations

from datetime import datetime, timedelta
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
                        f"lcd: {lcd_version.get('version', lcd_version)['firmware']} | "
                        f"fw: {rf_version.get('version', rf_version)['firmware']}"
                    )

        except AttributeError:
            pass

        return device

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the additional attrs."""
        attrs = super().extra_state_attributes
        if attrs is None:
            attrs = {}
        if self._surepy_entity.type == EntityType.PET:
            # Calcola la differenza tra il timestamp "since" e l'ora attuale
            if self._surepy_entity.location.since is not None:
                since_datetime = datetime.fromisoformat(self._surepy_entity.location.since)
                now = datetime.now()
                difference = now - since_datetime
                hours, remainder = divmod(difference.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                attrs["for"] = f"{hours:02d}:{minutes:02d}"
        return attrs


class Hub(SurePetcareBinarySensor):
    """Sure Petcare Hub."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        """Initialize a Sure Petcare Hub."""
        super().__init__(coordinator, _id, spc, BinarySensorDeviceClass.CONNECTIVITY)

        self._surepy_entity: SureHub = self._coordinator.data[_id]

        if self._attr_device_info:
            self._attr_device_info["identifiers"] = {(DOMAIN, str(self._id))}

        self._attr_available = self.is_on

    @property
    def is_on(self) -> bool:
        """Return True if the hub is on."""

        online: bool = False

        if self._surepy_entity:
            self._attr_extra_state_attributes = {
                "led_mode": int(self._surepy_entity.raw_data().get("status",{}).get("led_mode", 0)),
                "pairing_mode": bool(self._surepy_entity.raw_data().get("status",{}).get("pairing_mode", False)),
            }

            online = self._surepy_entity.online

        return online


class Pet(SurePetcareBinarySensor):
    """Sure Petcare Pet."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        """Initialize a Sure Petcare Pet."""

        super().__init__(coordinator, _id, spc, BinarySensorDeviceClass.PRESENCE)

        self._surepy_entity: SurePet = self._coordinator.data[_id]

        self._attr_entity_picture = self._surepy_entity.photo_url


    @property
    def is_on(self) -> bool:
        """Return True if the pet is at home."""

        inside: bool = False

        if self._surepy_entity:
            inside = bool(self._surepy_entity.location.where == Location.INSIDE)

        return inside


class DeviceConnectivity(SurePetcareBinarySensor):
    """Sure Petcare Connectivity Sensor."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        """Initialize a Sure Petcare device connectivity sensor."""

        super().__init__(coordinator, _id, spc, BinarySensorDeviceClass.CONNECTIVITY)

        self._surepy_entity: SurepyDevice = self._coordinator.data[_id]
        self._attr_name = f"{self._attr_name} Connectivity"
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}-connectivity"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the additional attrs."""

        attrs: dict[str, Any] = {}

        if self._surepy_entity and (
            state:= self._surepy_entity.raw_data().get("status")
        ):
            attrs = {
                "device_rssi": f'{state.get("signal",{}).get("device_rssi", 0):.2f}',
                "hub_rssi": f'{state.get("signal",{}).get("hub_rssi", 0):.2f}',
            }

        return attrs

    @property
    def is_on(self) -> bool:
        """Return True if the device is connected."""
        return bool(self.extra_state_attributes)
