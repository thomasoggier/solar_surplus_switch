import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SolarSurplusBaseSensor(SensorEntity, RestoreEntity):
    """Classe de base pour lier les capteurs au contrôleur."""

    def __init__(self, controller, entry, name_suffix, unique_id_suffix, icon=None):
        self._controller = controller
        self._attr_name = f"{entry.title} {name_suffix}"
        self._attr_unique_id = f"solar_surplus_{unique_id_suffix}_{entry.entry_id}"
        self._attr_icon = icon
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Custom",
            "model": "Solar Surplus Controller",
        }
        self._controller.register(self)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()):
            # Restauration éventuelle si nécessaire
            pass


class SolarSurplusStatusSensor(SolarSurplusBaseSensor):
    """Capteur affichant le statut textuel (feedback)."""
    def __init__(self, controller, entry):
        super().__init__(controller, entry, "Statut", "status", icon="mdi:text-box-outline")

    @property
    def native_value(self):
        return self._controller.status_message


class SolarSurplusExportPowerSensor(SolarSurplusBaseSensor):
    """Capteur affichant la puissance d'exportation mesurée."""
    def __init__(self, controller, entry):
        super().__init__(controller, entry, "Puissance Export", "export_power", icon="mdi:solar-power")
        self._attr_native_unit_of_measurement = "W"
        self._attr_state_class = "measurement"

    @property
    def native_value(self):
        return round(self._controller.current_export, 1)


class SolarSurplusPriorityActiveSensor(SolarSurplusBaseSensor):
    """Capteur indiquant si la priorité est active (True/False ou On/Off)."""
    def __init__(self, controller, entry):
        super().__init__(controller, entry, "Priorité Active", "priority_active", icon="mdi:priority-high")

    @property
    def native_value(self):
        return "ON" if self._controller.is_priority() else "OFF"


class SolarSurplusOutputStateSensor(SolarSurplusBaseSensor):
    """Capteur affichant l'état réel de la sortie."""
    def __init__(self, controller, entry):
        super().__init__(controller, entry, "État Sortie", "output_state", icon="mdi:power-socket-eu")

    @property
    def native_value(self):
        return "ON" if self._controller.is_on else "OFF"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the solar surplus sensors."""
    # Récupération du contrôleur partagé depuis le domaine
    # (Assurez-vous que votre switch.py ou __init__.py enregistre bien controller dans hass.data[DOMAIN][entry.entry_id]["controller"])
    data = hass.data[DOMAIN].get(entry.entry_id, {})
    controller = data.get("controller")

    if not controller:
        _LOGGER.error("Impossible de trouver le contrôleur SolarSurplus pour initialiser les capteurs.")
        return

    async_add_entities([
        SolarSurplusStatusSensor(controller, entry),
        SolarSurplusExportPowerSensor(controller, entry),
        SolarSurplusPriorityActiveSensor(controller, entry),
        SolarSurplusOutputStateSensor(controller, entry),
    ])