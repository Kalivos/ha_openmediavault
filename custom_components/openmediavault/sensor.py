"""The openmediavault sensor integration."""
import logging
from datetime import timedelta

import voluptuous as vol
import json
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
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=30)
ERROR_CODE_NOT_AUTHENTICATED = 5000
ERROR_CODE_SESSION_EXPIRED = 5001

ATTR_HOSTNAME = 'hostname'
ATTR_VERSION = 'version'
ATTR_PROCESSOR = 'cpumodelname'
ATTR_KERNEL = 'kernel'
ATTR_SYSTEM_TIME = 'time'
ATTR_UPTIME = 'uptime'
ATTR_LOAD_AVERAGE = 'loadaverage'
ATTR_CPU_USAGE = 'cpuusage'
ATTR_MEMORY_USAGE = 'memused'

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


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the openmediavault sensor."""

    name = config.get(CONF_NAME)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    host = config.get(CONF_HOST)
    conditions = config.get(CONF_MONITORED_CONDITIONS)
    session = requests.Session()
    api = OpenMediaVaultAPI(host, session, username, password, conditions)

    dev = []
    for condition in conditions:
        dev.append(OpenMediaVaultSensor(api, name, condition))

    async_add_entities(dev, True)


class OpenMediaVaultSensor(Entity):
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
    def state_attributes(self):
        """Return the attributes of the sensor."""
        return {'friendly_name': self._var_omv_name}

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._var_icon

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def available(self):
        """Return availability of OMV API."""
        return self._api.available

    async def async_update(self):
        """Fetch new state data for the sensor."""
        self._api.update()
        if self.available:
            self._state = self._api.data[self._var_name]
        else:
            self._state = None


class OpenMediaVaultAPI:
    """Get the latest data and update the states."""

    def __init__(self, host, session, username, password, conditions):
        """Initialize the data object."""
        self.resource = "{}{}".format(host, ENDPOINT)

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

        self.username = username
        self.password = password
        self.raw_data = None
        self.conditions = conditions
        self.available = True
        self.session = session
        self.login()

    def login(self):
        """Responsible for handling the login to openmediavault."""

        try:
            response = self.session.post(self.resource, data=json.dumps({
                'service': 'session',
                'method': 'login',
                'params': {
                    'username': self.username,
                    'password': self.password
                }
            }))

            self.raw_data = response.json()

            _LOGGER.debug("Response from openmediavault login: %s", self.raw_data)
            if self.raw_data['error'] is not None:
                _LOGGER.error("Unable to login to openmediavault")
                _LOGGER.error(self.raw_data['error']['message'])

        except requests.exceptions.ConnectionError as e:
            _LOGGER.error("Unable to login to openmediavault")
            _LOGGER.error(e)

    def get_system_information(self):
        """Get the latest data from OMV server."""

        try:
            response = self.session.post(self.resource, data=json.dumps({
                'service': 'System',
                'method': 'getInformation',
                'params': {},
                'options': {
                    'updatelastaccess': False
                }
            }))

            self.raw_data = response.json()
            _LOGGER.debug("Response from OMV get_system_information():  %s", self.raw_data)

            error_check = self.error_check(self.raw_data)

        except requests.exceptions.ConnectionError:
            _LOGGER.warning("Unable to fetch data from openmediavault")
            self.available = False
            self.raw_data = None

        if error_check['retry']:
            self.get_system_information()
        else:
            self.format_system_information()
            self.available = True

    def format_system_information(self):
        """Format raw data into easily accessible dictionary"""

        if self.raw_data is not None and self.raw_data['response'] is not None:
            response = self.raw_data['response']
            for attr_key in response:
                prop = attr_key.lower().replace(" ", "_")
                if isinstance(response[attr_key], dict):
                    # Unlikely that a dictionary will be returned, may not work as expected
                    self.data[prop] = response[attr_key]['value']
                else:
                    self.data[prop] = response[attr_key]

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Fetch new state data for the sensor."""

        self.get_system_information()

    def error_check(self, response):
        """Parse the response and check for any known errors."""

        retry = False

        if response is not None and response['error'] is not None:
            error_code = response['error']['code']

            if error_code == ERROR_CODE_NOT_AUTHENTICATED or error_code == ERROR_CODE_SESSION_EXPIRED:
                _LOGGER.debug("Session expired. Signing back in.")
                self.login()
                retry = True

        return {'retry': retry}