"""Device tracker for SureHA pets."""
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepy.entities import EntityType
from surepy.entities.pet import Pet as SurePet
from surepy.enums import Location

# pylint: disable=relative-beyond-top-level
from . import DOMAIN, SurePetcareAPI
from .const import SPC

_LOGGER = logging.getLogger(__name__)

SOURCE_TYPE_FLAP = "flap"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Pet tracker from config entry."""

    spc: SurePetcareAPI = hass.data[DOMAIN][SPC]

    async_add_entities(
        [
            SureDeviceTracker(spc.coordinator, pet.id, spc)
            for pet in spc.coordinator.data.values()
            if pet.type == EntityType.PET
        ],
    )


class SureDeviceTracker(CoordinatorEntity, ScannerEntity):
    """Pet device tracker."""

    _attr_force_update = False
    _attr_icon = "mdi:cat"

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        """Initialize the tracker."""
        super().__init__(coordinator)

        self._spc: SurePetcareAPI = spc
        self._coordinator = coordinator

        if _id is None:
            raise ValueError("Pet ID is required")											  
        self._id = _id
        self._attr_unique_id = f"{self._id}_pet_tracker"

        self._surepy_entity: SurePet = self._coordinator.data[self._id]
        type_name = self._surepy_entity.type.name.replace("_", " ").title()
        name: str = (
            self._surepy_entity.name
            if self._surepy_entity.name
            else f"Unnamed {type_name}"
        )

        self._attr_name: str = f"{type_name} {name}"

        # picture of the pet that can be added via the sure app/website
        self._attr_entity_picture = self._surepy_entity.photo_url

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected to the network."""
        return bool(self.location_name == "home")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the additional attrs."""

        attrs: dict[str, Any] = {}

        if pet := self._coordinator.data[self._id]:
            attrs = {
                "since": pet.location.since,
                "where": pet.location.where,
                **pet.raw_data(),
            }

            # Calcola la differenza tra il timestamp "since" e l'ora attuale
            if self._surepy_entity.location.since is not None:
                since_datetime = datetime.fromisoformat(self._surepy_entity.location.since)
                now = datetime.now()
                difference = now - since_datetime
                hours, remainder = divmod(difference.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                attrs["for"] = f"{hours:02d}:{minutes:02d}"

        return attrs

    @property
    def location_name(self) -> str:
        """Return 'home' if the pet is at home."""

		pet: SurePet			
        inside: bool = False

        if pet := self._coordinator.data[self._id]:
            inside = bool(pet.location.where == Location.INSIDE)

        return "home" if inside else "not_home"

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the pet."""
        return SOURCE_TYPE_FLAP