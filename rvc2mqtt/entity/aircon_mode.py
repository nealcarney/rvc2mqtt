"""
A air conditioner mode entity linked to a thermostat

Copyright 2022 Sean Brogan
SPDX-License-Identifier: Apache-2.0

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""

from enum import Enum
import logging
import struct
from rvc2mqtt.mqtt import MQTT_Support
from rvc2mqtt.entity import EntityPluginBaseClass

class HvacMode(Enum):
    '''
    simple class for the HVAC Mode which includes cool, dry and off
    
    '''
    OFF = 'off'
    COOL = 'cool'
    HEAT = 'heat'                  
    DRY = 'dry'               

    @property
    def rvc_mode_for_rvc_msg(self) -> str:
        # Either heat or off; cool and dry are not supported by aircon
        if self == HvacMode.COOL:
            return 3
        elif self == HvacMode.DRY:
            return 6
        else:
            return 0

    @staticmethod
    def get_hvac_mode_from_rvc(rvc_mode:str):
        if rvc_mode == "window defrost/dehumidify":
            return HvacMode.DRY
        else:
            return HvacMode(rvc_mode)

class AIRCON_MODE_THERMOSTAT_STATUS_1(EntityPluginBaseClass):
    FACTORY_MATCH_ATTRIBUTES = {"name": "THERMOSTAT_STATUS_1", "type": "aircon_mode"}
    """
    A air conditioner mode entity linked to a thermostat
    """

    def __init__(self, floorplan_info: dict, mqtt_support: MQTT_Support):
        self.id = "aircon-mode-i" + str(floorplan_info["instance"])
        super().__init__(floorplan_info, mqtt_support)
        self.Logger = logging.getLogger(__class__.__name__)
        self.name =  floorplan_info["instance_name"]
        self.link_id = floorplan_info["link_id"]
        self.rvc_instance = floorplan_info['instance']
        self.status_data = ""
        self.command_data = ""
        self._mode = HvacMode.OFF
        self._changed = True
        self.thermostat_entity_link = None

        # RVC message must match the following to be this device
        self.rvc_match_status = { "name": "THERMOSTAT_STATUS_1", "instance": floorplan_info['instance']}
        self.rvc_match_command = { "name": "THERMOSTAT_COMMAND_1", "instance": floorplan_info['instance']}

    @property
    def mode(self) -> HvacMode:
        return self._mode

    @mode.setter
    def mode(self, value: HvacMode):
        if value != self._mode:
            self._mode = value
            self._changed = True

    def process_rvc_msg(self, new_message: dict) -> bool:
        if self._is_entry_match(self.rvc_match_status, new_message):
            # Log if data has changed
            if self.status_data != new_message["data"]:
                self.status_data = new_message["data"]
                self.Logger.debug(f"New Status: {str(new_message)}")
            self.mode = HvacMode.get_hvac_mode_from_rvc(new_message["operating_mode_definition"])
            # Mode has changed; update mqtt
            if self._changed:
                self.Logger.debug(f"Notifying thermostat of aircon mode: {self.mode.value}") 
                self.thermostat_entity_link.update_thermostat_mode()
                self._changed = False
                # Since mode has changed, trigger update thermostat entity action
                self.Logger.debug(f"Aircon mode calling update of thermostat link\r\n")
                self.thermostat_entity_link.update_thermostat_action()
            return True
        elif self._is_entry_match(self.rvc_match_command, new_message):
            # Log if data has changed
            if self.command_data != new_message["data"]:
                self.command_data = new_message["data"]
                self.Logger.debug(f"New Command: {str(new_message)}")
            return False

    def process_mqtt_msg(self, payload):
        """ Receive mqtt incoming command message transmitted via the thermostat entity

            convert the new value into entity format
            make an rvc command message with the new value 
            queue it
               
        """
        try:
            mode = HvacMode(payload.lower())
            self.Logger.debug(f"Aircon received mode {mode}")
            mi = mode.rvc_mode_for_rvc_msg
            fmi = 0
            smi = 0
            fsi = 0
            temp = 65535
            self.Logger.debug(f"Sending mode {mi} for instance {self.rvc_instance}")
            msg_bytes = bytearray(8)
            struct.pack_into("<BBBHHB", msg_bytes, 0, self.rvc_instance, (mi | (fmi << 4) | (smi << 6)), fsi, temp, temp, 0  )
            self.send_queue.put({"dgn": "1FEF9", "data": msg_bytes})

        except Exception as e:
            self.Logger.error(f"Exception trying to respond to aircon mode + {str(e)}")
