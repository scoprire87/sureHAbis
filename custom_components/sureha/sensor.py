"""Support for Sure PetCare Flaps/Pets sensors."""
from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_VOLTAGE,
    UnitOfMass,
    PERCENTAGE,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepy.entities import SurepyEntity
from surepy.entities.devices import (
    Feeder as SureFeeder,
    FeederBowl as SureFeederBowl,
    Felaqua as SureFelaqua,
    Flap as SureFlap,
    SurepyDevice,
)
from surepy.enums import EntityType, LockState

# pylint: disable=relative-beyond-top-level
from . import SurePetcareAPI
from .const import (
    ATTR_VOLTAGE_FULL,
    ATTR_VOLTAGE_LOW,
    DOMAIN,
    SPC,
    SURE_BATT_VOLTAGE_FULL,
    SURE_BATT_VOLTAGE_LOW,
    SURE_MANUFACTURER,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 2


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: Any,
    discovery_info: Any = None,
) -> None:
    """Set up Sure PetCare sensor platform."""
    await async_setup_entry(hass, config, async_add_entities)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: Any
) -> None:
    """Set up config entry Sure Petcare Flaps sensors."""

    entities: list[Flap | Felaqua | Feeder | FeederBowl | Battery] = []

    spc: SurePetcareAPI = hass.data[DOMAIN][SPC]

    for surepy_entity in spc.coordinator.data.values():

        if surepy_entity.type in [
            EntityType.CAT_FLAP,
            EntityType.PET_FLAP,
        ]:
            entities.append(Flap(spc.coordinator, surepy_entity.id, spc))

        elif surepy_entity.type == EntityType.FELAQUA:
            entities.append(Felaqua(spc.coordinator, surepy_entity.id, spc))

        elif surepy_entity.type == EntityType.FEEDER:

            for bowl in surepy_entity.bowls.values():
                entities.append(
                    FeederBowl(spc.coordinator, surepy_entity.id, spc, bowl.raw_data())
                )

            entities.append(Feeder(spc.coordinator, surepy_entity.id, spc))

        if surepy_entity.type in [
            EntityType.CAT_FLAP,
            EntityType.PET_FLAP,
            EntityType.FEEDER,
            EntityType.FELAQUA,
        ]:

            voltage_batteries_full = cast(
                float,
                config_entry.options.get(ATTR_VOLTAGE_FULL, SURE_BATT_VOLTAGE_FULL),
            )
            voltage_batteries_low = cast(
                float, config_entry.options.get(ATTR_VOLTAGE_LOW, SURE_BATT_VOLTAGE_LOW)
            )

            entities.append(
                Battery(
                    spc.coordinator,
                    surepy_entity.id,
                    spc,
                    voltage_full=voltage_batteries_full,
                    voltage_low=voltage_batteries_low,
                )
            )

    async_add_entities(entities)


class SurePetcareSensor(CoordinatorEntity, SensorEntity):
    """A binary sensor implementation for Sure Petcare Entities."""

    _attr_should_poll = False

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        """Initialize a Sure Petcare sensor."""
        super().__init__(coordinator)

        self._id = _id
        self._spc: SurePetcareAPI = spc

        self._coordinator = coordinator

        self._surepy_entity: SurepyEntity = self._coordinator.data[_id]
        self._attr_available = bool(self._surepy_entity.raw_data().get("status"))
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}"

        self._attr_extra_state_attributes = (
            {**self._surepy_entity.raw_data()} if self._attr_available else {}
        )

        self._attr_name: str = (
            f"{self._surepy_entity.type.name.replace('_', ' ').title()} "
            f"{self._surepy_entity.name.capitalize()}"
        )

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

            if self._attr_available:
                versions = self._surepy_entity.raw_data().get("status", {}).get("version", {})

                if dev_fw_version := versions.get("device", {}).get("firmware"):
                    device["sw_version"] = dev_fw_version

                if (lcd_version := versions.get("lcd", {})) and (
                    rf_version := versions.get("rf", {})
                ):
                    device["sw_version"] = (
                        f"lcd: {lcd_version.get('version', lcd_version)['firmware']} | "
                        f"fw: {rf_version.get('version', rf_version)['firmware']}"
                    )

        except AttributeError as e:
            _LOGGER.exception(f"Error getting device info: {e}")

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


class Flap(SurePetcareSensor):
    """Sure Petcare Flap."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        super().__init__(coordinator, _id, spc)
        self._surepy_entity: SureFlap = self._coordinator.data[_id]

        self._attr_entity_picture = self._surepy_entity.icon
        self._attr_unit_of_measurement = None

        if self._attr_available:
            self._attr_extra_state_attributes = {
                "learn_mode": bool(self._surepy_entity.raw_data().get("status",{}).get("learn_mode",False)),
                **self._surepy_entity.raw_data(),
            }

            if locking := self._surepy_entity.raw_data().get("status",{}).get("locking"):
                self._attr_state = LockState(locking["mode"]).name.casefold()

    @property
    def _attr_state(self) -> LockState | None:
        if state := self._surepy_entity.raw_data().get("status"):
            return LockState(state["locking"]["mode"])


class Felaqua(SurePetcareSensor):
    """Sure Petcare Felaqua."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        super().__init__(coordinator, _id, spc)
        self._surepy_entity: SureFelaqua = self._coordinator.data[_id]

        self._attr_entity_picture = self._surepy_entity.icon
        self._attr_unit_of_measurement = UnitOfVolume.MILLILITERS

    @property
    def _attr_state(self) -> float | None:
        if felaqua := self._surepy_entity: # No need to cast, already typed
            return int(felaqua.water_remaining) if felaqua.water_remaining else None


class FeederBowl(SurePetcareSensor):
    """Sure Petcare Feeder Bowl."""

    def __init__(
        self,
        coordinator,
        feeder_id: int,  # Renamed for clarity
        spc: SurePetcareAPI,
        bowl_data: dict[str, int | str],
    ):
        """Initialize a Bowl sensor."""
        super().__init__(coordinator, feeder_id, spc)  # Use feeder_id here
        self._feeder_id = feeder_id  # Renamed
        self.bowl_id = int(bowl_data["index"])
        self._bowl_entity_id = int(f"{feeder_id}{str(self.bowl_id)}")  # Renamed
        self._surepy_feeder_entity: SurepyEntity = self._coordinator.data[feeder_id]
        self._surepy_entity: SureFeederBowl = self._coordinator.data[feeder_id].bowls[self.bowl_id]
        # ... (rest of __init__)

    @property
    def _attr_state(self) -> int | None:  # Use _attr_state
        if (feeder := cast(SureFeeder, self._coordinator.data[self._feeder_id])) and (
            weight := feeder.bowls[self.bowl_id].weight
        ):
            return int(weight) if weight is not None else 0 # Return 0 instead of None


class Feeder(SurePetcareSensor):
    """Sure Petcare Feeder."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        super().__init__(coordinator, _id, spc)

        self._surepy_entity: SureFeeder

        self._attr_entity_picture = self._surepy_entity.icon
        self._attr_unit_of_measurement = UnitOfMass.GRAMS

    @property
    def _attr_state(self) -> float | None:  # Use _attr_state
        if feeder := cast(SureFeeder, self._coordinator.data[self._id]):
            return int(feeder.total_weight) if feeder.total_weight else None


class Battery(SurePetcareSensor):
    """Sure Petcare Flap."""

    def __init__(
        self,
        coordinator,
        _id: int,
        spc: SurePetcareAPI,
        voltage_full: float,
        voltage_low: float,
    ):
        super().__init__(coordinator, _id, spc)
        self._surepy_entity: SurepyDevice = self._coordinator.data[_id] # Type the entity
        self._attr_name = f"{self._attr_name} Battery Level"
        self.voltage_low = voltage_low
        self.voltage_full = voltage_full
        self._attr_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._surepy_entity.id}-battery"
        self._battery_level = self._surepy_entity.calculate_battery_level(voltage_full=self.voltage_full, voltage_low=self.voltage_low)
        self._voltage = float(self._surepy_entity.raw_data().get("status",{}).get("battery", 0)) # Default to 0 to avoid errors

    @property
    def _attr_state(self) -> int | None:  # Use _attr_state
        return self._battery_level

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the additional attrs."""

        return {
            "battery_level": self._battery_level,
            ATTR_VOLTAGE: f"{self._voltage:.2f}",
            f"{ATTR_VOLTAGE}_per_battery": f"{self._voltage / 4:.2f}",
        }
