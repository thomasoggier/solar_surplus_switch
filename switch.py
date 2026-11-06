import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    CONF_EXPORT_SENSOR,
    CONF_TARGET_SWITCH,
    CONF_POWER_THRESHOLD,
    CONF_DELAY_ON,
    CONF_DELAY_OFF,
    CONF_PRIORITY_SENSOR,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    _LOGGER.debug("Configuration de l'entrée %s (setup_entry)", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})
    controller = SolarSurplusController(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {"controller": controller}

    async_add_entities([
        SolarSurplusControllerSwitch(controller, entry),
        SolarSurplusAutomationModeSwitch(controller, entry),
    ])
    _LOGGER.debug("Entités switch créées et ajoutées avec succès pour l'entrée %s", entry.entry_id)

class SolarSurplusController:
    def __init__(self, hass, entry):
        self.hass = hass
        self.export_sensor = entry.options.get(CONF_EXPORT_SENSOR, entry.data.get(CONF_EXPORT_SENSOR))
        self.target_switch = entry.options.get(CONF_TARGET_SWITCH, entry.data.get(CONF_TARGET_SWITCH))
        self.power_threshold = entry.options.get(CONF_POWER_THRESHOLD, entry.data.get(CONF_POWER_THRESHOLD))
        self.delay_on = entry.options.get(CONF_DELAY_ON, entry.data.get(CONF_DELAY_ON))
        self.delay_off = entry.options.get(CONF_DELAY_OFF, entry.data.get(CONF_DELAY_OFF))
        self.priority_sensor = entry.options.get(CONF_PRIORITY_SENSOR, entry.data.get(CONF_PRIORITY_SENSOR))

        self.is_on = False
        self.automation_enabled = True
        self.current_export = 0.0
        self.status_message = "Initialisation"
        self._timer = None
        self._listeners = []

    def register(self, listener):
        self._listeners.append(listener)

    def notify(self):
        for l in self._listeners:
            if hasattr(l, "async_write_ha_state"):
                l.async_write_ha_state()

    def is_priority(self) -> bool:
        if not self.priority_sensor:
            return False
        st = self.hass.states.get(self.priority_sensor)
        return st and st.state.lower() in ("on", "charging", "true")

    async def call_target(self, state: bool):
        if not self.target_switch:
            _LOGGER.warning("Aucun switch cible configuré !")
            return
        domain, entity_id = self.target_switch.split(".", 1) if "." in self.target_switch else ("switch", self.target_switch)
        service = "turn_on" if state else "turn_off"
        _LOGGER.debug("Appel du service %s.%s sur la cible %s.%s", domain, service, domain, entity_id)
        await self.hass.services.async_call(domain, service, {"entity_id": f"{domain}.{entity_id}"}, blocking=False)

    async def set_state(self, state: bool, manual: bool = False, msg: str = None):
        if manual and self.automation_enabled:
            _LOGGER.warning("Modification manuelle refusée : le mode automatique est actif.")
            return

        if self._timer:
            self._timer()
            self._timer = None

        if self.is_on != state:
            self.is_on = state
            await self.call_target(state)

        if not self.automation_enabled:
            self.status_message = "Mode Manuel"
        else:
            self.status_message = msg or ("Switch actif (Auto)" if self.is_on else "En attente de surplus")

        self.notify()

    async def evaluate(self, *args):
        _LOGGER.debug("Évaluation du surplus -> export: %.1fW, threshold: %.1fW, auto: %s, is_on: %s",
                      self.current_export, self.power_threshold, self.automation_enabled, self.is_on)

        if not self.automation_enabled:
            if self._timer:
                self._timer()
                self._timer = None
            if self.status_message != "Mode Manuel":
                self.status_message = "Mode Manuel"
                self.notify()
            return

        if self.is_priority():
            if self._timer:
                self._timer()
                self._timer = None
            await self.set_state(False, msg="Priorité active")
            return

        required_threshold = 0.0 if self.is_on else self.power_threshold
        surplus_ok = self.current_export >= required_threshold

# 1. Surplus suffisant et appareil éteint -> Lancer le timer d'enclenchement
        if surplus_ok and not self.is_on:
            if not self._timer:
                _LOGGER.debug("Démarrage du délai d'enclenchement de %ss...", self.delay_on)
                self.status_message = "En attente d'enclenchement..."
                self.notify()
                
                @callback
                def _on_timer(_):
                    self.hass.async_create_task(self._execute_state(True))
                
                self._timer = async_call_later(self.hass, self.delay_on, _on_timer)

        # 2. Surplus insuffisant et appareil allumé -> Lancer le timer de coupure
        elif not surplus_ok and self.is_on:
            if not self._timer:
                _LOGGER.debug("Démarrage du délai de coupure de %ss...", self.delay_off)
                self.status_message = "En attente de coupure..."
                self.notify()
                
                @callback
                def _off_timer(_):
                    self.hass.async_create_task(self._execute_state(False))
                
                self._timer = async_call_later(self.hass, self.delay_off, _off_timer)
        # 3. Situation stable
        else:
            # On ne nettoie le timer QUE si la condition n'exige plus aucun changement
            if self._timer and ((surplus_ok and self.is_on) or (not surplus_ok and not self.is_on)):
                _LOGGER.debug("Situation stable, annulation du timer en cours.")
                self._timer()
                self._timer = None
            
            if not self._timer:
                self.status_message = "Switch actif (Auto)" if self.is_on else "En attente de surplus"
                self.notify()
    async def _execute_state(self, state: bool):
        """Exécute le changement d'état après expiration du minuteur."""
        self._timer = None
        await self.set_state(state)
        await self.evaluate()

class SolarSurplusControllerSwitch(SwitchEntity, RestoreEntity):
    def __init__(self, c, entry):
        self.c = c
        self._attr_name = f"{entry.title} Sortie"
        self._attr_unique_id = f"solar_surplus_controller_{entry.entry_id}"
        self._attr_icon = "mdi:power-plug"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": entry.title, "manufacturer": "Custom"}
        c.register(self)

    @property
    def is_on(self): return self.c.is_on
    @property
    def extra_state_attributes(self):
        return {
            "feedback": self.c.status_message,
            "automation_mode": "Automatique" if self.c.automation_enabled else "Manuel",
            "export_power_w": self.c.current_export
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if (st := await self.async_get_last_state()):
            self.c.is_on = (st.state == "on")
        
        if (st := self.c.hass.states.get(self.c.export_sensor)):
            try:
                val = float(st.state)
                unit = st.attributes.get("unit_of_measurement", "W").lower()
                self.c.current_export = val * 1000.0 if unit in ("kw", "kilowatt") else val
            except ValueError:
                pass

        self.async_on_remove(async_track_state_change_event(self.c.hass, [self.c.export_sensor], self._changed))
        if self.c.priority_sensor:
            self.async_on_remove(async_track_state_change_event(self.c.hass, [self.c.priority_sensor], self._changed))

    @callback
    async def _changed(self, event):
        entity_id = event.data.get("entity_id")
        st = event.data.get("new_state")
        if not st:
            return

        if entity_id == self.c.export_sensor:
            try:
                val = float(st.state)
                unit = st.attributes.get("unit_of_measurement", "W").lower()
                self.c.current_export = val * 1000.0 if unit in ("kw", "kilowatt") else val
            except ValueError:
                pass

        await self.c.evaluate()

    async def async_turn_on(self, **kwargs):
        await self.c.set_state(True, manual=True)

    async def async_turn_off(self, **kwargs):
        await self.c.set_state(False, manual=True)


class SolarSurplusAutomationModeSwitch(SwitchEntity, RestoreEntity):
    def __init__(self, c, entry):
        self.c = c
        self._attr_name = f"{entry.title} Mode Automatique"
        self._attr_unique_id = f"solar_surplus_auto_{entry.entry_id}"
        self._attr_icon = "mdi:auto-mode"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": entry.title, "manufacturer": "Custom"}
        c.register(self)

    @property
    def is_on(self): return self.c.automation_enabled

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if (st := await self.async_get_last_state()):
            self.c.automation_enabled = (st.state == "on")
        # Suppression de l'appel direct à evaluate() ici pour éviter le RuntimeError

    async def async_turn_on(self, **kwargs):
        _LOGGER.debug("Activation du mode Automatique par l'utilisateur")
        self.c.automation_enabled = True
        self.c.notify()
        await self.c.evaluate()

    async def async_turn_off(self, **kwargs):
        _LOGGER.debug("Désactivation du mode Automatique (Mode Manuel)")
        self.c.automation_enabled = False
        if self.c._timer:
            self.c._timer()
            self.c._timer = None
        self.c.status_message = "Mode Manuel"
        self.c.notify()