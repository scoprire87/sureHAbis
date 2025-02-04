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
from. import SurePetcareAPI
from.const import DOMAIN, SPC, SURE_MANUFACTURER

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

    entities: list[SurePetcareBinarySensor] =  # Corretto: lista inizializzata

    spc: SurePetcareAPI = hass.data[DOMAIN][SPC]

    for surepy_entity in spc.coordinator.data.values():

        if surepy_entity.type == EntityType.PET:
            entities.append(Pet(spc.coordinator, surepy_entity.id, spc))

        elif surepy_entity.type == EntityType.HUB:
            entities.append(Hub(spc.coordinator, surepy_entity.id, spc))

        elif surepy_entity.type in [EntityType.PET_FLAP, EntityType.CAT_FLAP, EntityType.FEEDER, EntityType.FELAQUA]:
            entities.append(DeviceConnectivity(spc.coordinator, surepy_entity.id, spc))

    async_add_entities(entities)


#... (il resto del codice rimane invariato)
