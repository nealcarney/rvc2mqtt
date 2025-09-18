"""
Water Heater support

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

import math
import logging
import struct
import json
from rvc2mqtt.mqtt import MQTT_Support
from rvc2mqtt.entity import EntityPluginBaseClass

'''


Water Heater Command
This DGN provides external control of the water heater. Table 6.9.3a defines the DG attributes, and Table 6.9.3b defines the 
signal and parameter attributes.
An instance of zero indicates that the settings should be applied to all water heater instances. Values of 255 (or 65535) indicate 
that the particular datum should not be changed

'''

class WaterHeaterClass(EntityPluginBaseClass):
    '''
    Water Heater based on WATERHEATER_STATUS and WATERHEATER_COMMAND DGNs
    Multi instance device

    This is tailored specifically for the Truma AquaGo water heater

    Water heater:  
        Mode
        Temperature setpoint

    Binary Sensor: 
        DC power warning (shows error if power or gas is off )

    
    '''
    FACTORY_MATCH_ATTRIBUTES = {"name": "WATERHEATER_STATUS", "type": "water_heater"}

    def __init__(self, floorplan_info: dict, mqtt_support: MQTT_Support):
        self.id = f"waterheater-i" + str(floorplan_info["instance"])
        super().__init__(floorplan_info, mqtt_support)
        self.Logger = logging.getLogger(__class__.__name__)

        # Allow MQTT to control mode
        self.status_mode_topic = mqtt_support.make_device_topic_string(self.id, "mode", True)
        self.command_mode_topic = mqtt_support.make_device_topic_string(self.id, "mode", False)
        self.mqtt_support.register(self.command_mode_topic, self.process_mqtt_msg)

        # Allow MQTT to control set point temperature
        self.status_temp_topic = mqtt_support.make_device_topic_string(self.id, "temp", True)
        self.command_temp_topic = mqtt_support.make_device_topic_string(self.id, "temp", False)
        self.mqtt_support.register(self.command_temp_topic, self.process_mqtt_msg)

        # Status for sensor device
        self.status_dc_warning_topic = mqtt_support.make_device_topic_string(self.id, "dc_warning", True)

        # RVC message must match the following status or command
        self.rvc_match_status = {"name": "WATERHEATER_STATUS", "instance": floorplan_info['instance']}
        self.rvc_match_command = {"name": "WATERHEATER_COMMAND", "instance": floorplan_info['instance']}

        self.Logger.debug(f"Must match: {str(self.rvc_match_status)} or {str(self.rvc_match_command)}")
        
        # fields for a water heater object
        self.name = floorplan_info["instance_name"]
        self.instance = floorplan_info['instance']
        self.mode = "unknown"  # (0,1,2) RVC mode 
        self.HA_mode = "unknown" # (off, eco, performance) HA mode 
        self.temp = 35.0 # R/W mqtt and RVC (deg c)
        self.dc_warning = "unknown" # RO mqtt and RVC (power ok, power low)

        self.device = {"manufacturer": "Firefly Integrations",
                       "identifiers": "Firefly",
                       "name": "Firefly",
                       "model": "G12"
                       }

    def process_rvc_msg(self, new_message: dict) -> bool:
        """ Process an incoming message and determine if it
        is of interest to this object.

        If relevant - Process the message and return True
        else - return False
        """
        '''
        {"dgn": "1FFF6", "data": "C8004028FFFFFFFF", "name": "WATERHEATER_COMMAND", "instance": 200, 
        "operating modes": 0, "operating modes definition": "off", "set point temperature": 49.0, 
        "set point temperature F": 120.2, "electric element level": "1111", "timestamp": "1758054132.1760516"}
        '''

        if self._is_entry_match(self.rvc_match_status, new_message):
            self.Logger.debug(f"Msg Match Status: {str(new_message)}")

            # Mode
            # Only update if mode has changed
            if new_message["operating_modes"] != self.mode:
                self.mode = new_message["operating_modes"]
                self.HA_mode = {0: "off", 1: "eco", 2: "performance"}.get(self.mode, "unknown")
                self.mqtt_support.client.publish(self.status_mode_topic, self.HA_mode, retain=True)

            # Temp
            # Only update if temp has changed and >= 35C (RVC reports -273C when off; need to retain prior value by ignoring)
            if (new_message["set_point_temperature"] != self.temp) and (new_message["set_point_temperature"] >= 35):
                self.temp = new_message["set_point_temperature"]
                self.mqtt_support.client.publish(self.status_temp_topic, self.temp, retain=True)

            # DC warning 00 means OFF and 10 means ON (status 10 can be due to either power switch off or gas off)
            # Only update if state has changed
            if new_message["dc_power_warning_status"] != self.dc_warning:
                self.dc_warning = new_message["dc_power_warning_status"]
                self.HA_dc_warning = {'00': "OFF", '10': "ON"}.get(self.dc_warning)
                self.mqtt_support.client.publish(self.status_dc_warning_topic, self.HA_dc_warning, retain=True)

            return True

        elif self._is_entry_match(self.rvc_match_command, new_message):
            # This is the command.  Just eat the message so it doesn't show up
            # as unhandled.
            self.Logger.debug(f"Msg Match Command: {str(new_message)}")
            return True

        return False

    def process_mqtt_msg(self, topic, payload):
        
        self.Logger.debug(f"MQTT Msg Received on topic {topic} with payload {payload}")

        if topic == self.command_mode_topic:
            # Only update if the mode is changing
            self.Logger.debug(f"Received HA mode command {payload}; current mode {self.HA_mode}/{self.mode}")
            if self.HA_mode != payload:
                self.Logger.debug(f"Payload different than current mode")
                self.HA_mode = payload
                # Don't change self.mode yet since HA won't update unless triggered by next RVC status message
                rvc_mode = {'off': 0, 'eco': 1, 'performance': 2}.get(payload, None)
                self.Logger.debug(f"Updated current modes {self.HA_mode}/{self.mode}")
                self._rvc_change_state(rvc_mode)

        elif topic == self.command_temp_topic:
            # Only update if the temp is changing
            self.Logger.debug(f"Received HA temp command {payload}; current temp {self.temp}")
            if round(float(payload),1) != int(self.temp):
                self.Logger.debug(f"Payload different than current temp")
                self.temp = round(float(payload),1)
                self.Logger.debug(f"Updated current temp {self.temp}")
                self._rvc_change_state(self.mode)

    def _rvc_change_state(self, rvc_mode):

        self.Logger.debug(f"Setting RVC mode to {rvc_mode} and Temp to {self.temp}")

        msg_bytes = bytearray(8)
        temp_value = int((self.temp + 273) / .03125) #Scaling per table 5.3; overkill since Truma only supports 1 degC increments
        struct.pack_into("<BBHBBBB", msg_bytes, 0, self.instance, rvc_mode, temp_value, 255, 255, 255, 255)
        self.send_queue.put({"dgn": "1FFF6", "data": msg_bytes})

    def initialize(self):

        # Heater - produce the HA MQTT discovery config json
        config = {"name": self.name,
                  "platform": "water_heater",
                  "modes": ['off', 'eco', 'performance'],
                  "mode_state_topic": self.status_mode_topic,
                  "mode_command_topic": self.command_mode_topic,
                  "temperature_state_topic": self.status_temp_topic,
                  "temperature_command_topic": self.command_temp_topic,
#                  "value_template": "{{ value_json }}",
                  "max_temp": 49,
                  "min_temp": 35,
                  "temperature_unit": "C",
                  "precision": 1,
                  "qos": 1, "retain": False,
                  "unique_id": self.unique_device_id,
                  "device": self.device}
        config.update(self.get_availability_discovery_info_for_ha())

        config_json = json.dumps(config)

        ha_config_topic = self.mqtt_support.make_ha_auto_discovery_config_topic(
            self.unique_device_id, "water_heater")

        # publish info to mqtt
        self.mqtt_support.client.publish(
            ha_config_topic, config_json, retain=True)

        # DC Power warning binary sensor  - produce the HA MQTT discovery config json for
        config = {"name": self.name + " health" , 
                  "state_topic": self.status_dc_warning_topic,
                  "device_class": "problem",
                  "qos": 1, "retain": False,
                  "payload_on": "ON",
                  "payload_off": "OFF",
                  "unique_id": self.unique_device_id + "dc_warning",
                  "device": self.device}
        config.update(self.get_availability_discovery_info_for_ha())

        config_json = json.dumps(config)

        ha_config_topic = self.mqtt_support.make_ha_auto_discovery_config_topic(
            self.unique_device_id, "binary_sensor", "dc_warning")

        # publish info to mqtt
        self.mqtt_support.client.publish(
            ha_config_topic, config_json, retain=True)