"""Platform for sensor integration."""
import logging
from datetime import timedelta

import voluptuous as vol
import requests

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_NAME, CONF_USERNAME, CONF_PASSWORD, CONF_HOST, CONF_MONITORED_CONDITIONS, STATE_UNKNOWN)
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

# The domain of your component. Should be equal to the name of your component.
DOMAIN = "openmediavault"
DEFAULT_USERNAME = 'admin'
ENDPOINT = '/rpc.php'
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=5)

ATTR_HOSTNAME = 'hostname'
ATTR_VERSION = 'version'
ATTR_PROCESSOR = 'processor'
ATTR_KERNEL = 'kernel'
ATTR_SYSTEM_TIME = 'system_time'
ATTR_UPTIME = 'uptime'
ATTR_LOAD_AVERAGE = 'load_average'
ATTR_CPU_USAGE = 'cpu_usage'
ATTR_MEMORY_USAGE = 'memory_usage'

MONITORED_CONDITIONS = {
    ATTR_HOSTNAME: [
        'Hostname',
        'mdi:web'
    ],
    ATTR_VERSION: [
        'Version',
        'mdi:web'
    ],
    ATTR_PROCESSOR: [
        'Processor',
        'mdi:web'
    ],
    ATTR_KERNEL: [
        'Kernel',
        'mdi:web'
    ],
    ATTR_SYSTEM_TIME: [
        'System time',
        'mdi:web'
    ],
    ATTR_UPTIME: [
        'Uptime',
        'mdi:web'
    ],
    ATTR_LOAD_AVERAGE: [
        'Load average',
        'mdi:web'
    ],
    ATTR_CPU_USAGE: [
        'CPU usage',
        'mdi:web'
    ],
    ATTR_MEMORY_USAGE: [
        'Memory usage',
        'mdi:web'
    ]
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DOMAIN): cv.string,
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_MONITORED_CONDITIONS,
                 default=list(MONITORED_CONDITIONS)):
    vol.All(cv.ensure_list, [vol.In(MONITORED_CONDITIONS)]),
})


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the OMV sensor."""
    name = config.get(CONF_NAME)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    host = config.get(CONF_HOST)
    conditions = config.get(CONF_MONITORED_CONDITIONS)

    api = OmvAPI(host, username, password, conditions)

    dev = []
    for condition in conditions:
        dev.append(OmvSensor(api, name, condition))

    add_entities(dev, True)


class OmvSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, api, name, condition):
        """Initialize the sensor."""
        variable_info = MONITORED_CONDITIONS[condition]

        self._var_name = condition
        self._var_omv_name = variable_info[0]
        self._var_icon = variable_info[1]

        self._api = api
        self._name = name
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return '{}_{}'.format(self._name, self._var_name)

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._var_icon

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._var_units

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def available(self):
        """Return availability of OMV API."""
        return self._api.available

    def update(self):
        """Fetch new state data for the sensor."""
        self._api.update()
        if self.available:
            self._state = self._api.data[self._var_name]
        else:
            self._state = None


class OmvAPI:
    """Get the latest data and update the states."""

    def __init__(self, host, username, password, conditions):
        """Initialize the data object."""
        resource = "{}{}".format(host, ENDPOINT)

        self.data = {
            ATTR_HOSTNAME: STATE_UNKNOWN,
            ATTR_VERSION: STATE_UNKNOWN,
            ATTR_PROCESSOR: STATE_UNKNOWN,
            ATTR_KERNEL: STATE_UNKNOWN,
            ATTR_SYSTEM_TIME: STATE_UNKNOWN,
            ATTR_UPTIME: STATE_UNKNOWN,
            ATTR_LOAD_AVERAGE: STATE_UNKNOWN,
            ATTR_CPU_USAGE: STATE_UNKNOWN,
            ATTR_MEMORY_USAGE: STATE_UNKNOWN
        }

        self._request = requests.Request('POST', resource).prepare()
        self.raw_data = None
        self.sys_info_lookup = None
        self.conditions = conditions
        self.available = True
        self.session = requests.Session()
        self.login(username, password)

    def login(self, username, password):
        """Responsible for handling the login to openmediavault."""

        data = {"service": "session", "method": "login", "params": {"username": username, "password": password}}

        try:
            response = self.session.send(self._request, data=data, timeout=10)
            self.raw_data = response.json()

            # TODO: Need to check the response message to verify that the login was successful
            _LOGGER.debug("Response from OMV login: " + self.raw_data)

        except (ValueError, requests.exceptions.ConnectionError):
            _LOGGER.error("Unable to login to openmediavault")


    def get_system_information(self):
        """Get the latest data from OMV server."""

        # Response
        # {"response": [{"name": "Hostname", "value": "openmediavault", "type": "string", "index": 0},
        #               {"name": "Version", "value": "4.1.23-1 (Arrakis)", "type": "string", "index": 1},
        #               {"name": "Processor", "value": "Intel(R) Core(TM) i7-4790 CPU @ 3.60GHz", "type": "string", "index": 2},
        #               {"name": "Kernel", "value": "Linux 4.19.0-0.bpo.5-amd64", "type": "string", "index": 3},
        #               {"name": "System time", "value": "Fri 19 Jul 2019 10:43:43 AM PDT", "type": "string", "index": 4},
        #               {"name": "Uptime", "value": "0 days 0 hours 55 minutes 24 seconds", "type": "string", "index": 5},
        #               {"name": "Load average", "value": "0.00, 0.05, 0.03", "type": "string", "index": 6},
        #               {"name": "CPU usage", "value": {"text": "0%", "value": 0}, "type": "progress", "index": 7},
        #               {"name": "Memory usage", "value": {"text": "3% of 7.48 GiB", "value": 3}, "type": "progress",
        #                "index": 8}], "error": null}

        data = {"service": "System", "method": "getInformation", "params": {}, "options": {"updatelastaccess": False}}

        try:
            response = self.session.send(self._request, data=data, timeout=10)
            self.raw_data = response.json()
            self.format_system_information()
            self.available = True

            _LOGGER.debug("Response from OMV get_system_information(): " + self.raw_data)
        except (ValueError, requests.exceptions.ConnectionError):
            _LOGGER.warning("Unable to fetch data from openmediavault")
            self.available = False
            self.raw_data = None

    def format_system_information(self):
        """Format raw data into easily accessible dictionary"""

        for attr_key in self.raw_data.response:
            if isinstance(attr_key.value, list):
                self.sys_info_lookup[attr_key.name] = attr_key.value.value
            else:
                self.sys_info_lookup[attr_key.name] = attr_key.value

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Fetch new state data for the sensor."""

        self.get_system_information()

        for attr_key in self.conditions:
            self.data[attr_key] = self.sys_info_lookup[attr_key[0]]
