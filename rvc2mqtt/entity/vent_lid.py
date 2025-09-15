"""
A vent lid button (up or down) that is linked to a vent fan entity

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


class VentLid_DC_DIMMER_STATUS_3(EntityPluginBaseClass):
    FACTORY_MATCH_ATTRIBUTES = {"name": "DC_DIMMER_STATUS_3", "type": "vent_lid"}
    """
    Vent lid switch that is tied to RVC DGN of DC_DIMMER_STATUS_3 and DC_DIMMER_COMMAND_2
    This entity should only be called by a linked fan entity
    It is not used in Home Assistant directly
    """

    def __init__(self, floorplan_info: dict, mqtt_support: MQTT_Support):
        self.id = "vent-lid-i" + str(floorplan_info["instance"])
        super().__init__(floorplan_info, mqtt_support)
        self.Logger = logging.getLogger(__class__.__name__)
        self.name =  floorplan_info["instance_name"]
        self.rvc_instance = floorplan_info['instance']
        self.duration = 20  # seconds to run the vent lid motor
        if "up" in self.name.lower():
            self.duration = 20
        elif "down" in self.name.lower():
            self.duration = 15
        else:
            self.Logger.error(f"Vent lid name {self.name} does not contain up or down")
        self.rvc_group = '11111111'
        if 'group' in floorplan_info:
            self.rvc_group = floorplan_info['group']

    def process_rvc_msg(self, new_message: dict) -> bool:
        return False

    def rvc_switch_off(self):
        #Command 3 (off)
        msg_bytes = bytearray(8)
        struct.pack_into("<BBBBBBH", msg_bytes, 0, self.rvc_instance, int(
            self.rvc_group, 2), 0, 3, 0xFF, 0, 0xFF)
        self.send_queue.put({"dgn": "1FEDB", "data": msg_bytes})

    def rvc_switch_on(self):
        #100% brightness (200), command 1 (ON duration), duration depends on up or down
        msg_bytes = bytearray(8)
        struct.pack_into("<BBBBBBH", msg_bytes, 0, self.rvc_instance, int(
            self.rvc_group, 2), 200, 1, self.duration, 0, 0xFF)
        self.send_queue.put({"dgn": "1FEDB", "data": msg_bytes})
