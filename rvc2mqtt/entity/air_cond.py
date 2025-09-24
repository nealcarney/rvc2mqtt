"""


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


import logging
import struct
import json
from rvc2mqtt.mqtt import MQTT_Support
from rvc2mqtt.entity import EntityPluginBaseClass


class TESTER2_AIR_CONDITIONER_STATUS(EntityPluginBaseClass):
    FACTORY_MATCH_ATTRIBUTES = {"name": "AIR_CONDITIONER_STATUS", "type": "test2"}
    """
    A test air conditioner entity
    """

    def __init__(self, floorplan_info: dict, mqtt_support: MQTT_Support):
        self.id = "test2-i" + str(floorplan_info["instance"])
        super().__init__(floorplan_info, mqtt_support)
        self.Logger = logging.getLogger(__class__.__name__)
        self.name =  floorplan_info["instance_name"]
        self.rvc_instance = floorplan_info['instance']
        self.status_data = ""
        self.command_data = ""

        # RVC message must match the following to be this device
        self.rvc_match_status = { "name": "AIR_CONDITIONER_STATUS", "instance": floorplan_info['instance']}
        self.rvc_match_command= { "name": "AIR_CONDITIONER_COMMAND", "instance": floorplan_info['instance']}

    def process_rvc_msg(self, new_message: dict) -> bool:
        if self._is_entry_match(self.rvc_match_status, new_message):
            if self.status_data != new_message["data"]:
                self.status_data = new_message["data"]
                self.Logger.debug(f"New Status: {str(new_message)}")

            return True
        elif self._is_entry_match(self.rvc_match_command, new_message):
            if self.command_data != new_message["data"]:
                self.command_data = new_message["data"]
                self.Logger.debug(f"New Command: {str(new_message)}")
        return False