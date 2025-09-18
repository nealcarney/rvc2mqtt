"""
A dimmer switch

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


class LightSwitch_DC_DIMMER_STATUS_3(EntityPluginBaseClass):
    FACTORY_MATCH_ATTRIBUTES = {"name": "DC_DIMMER_STATUS_3", "type": "dimmer_switch"}
    """
    Dimmer switch that is tied to RVC DGN of DC_DIMMER_STATUS_3 and DC_DIMMER_COMMAND_2
    """
    LIGHT_ON = "on"   #light status is lowercase only when using template schema
    LIGHT_OFF = "off"

    def __init__(self, floorplan_info: dict, mqtt_support: MQTT_Support):
        self.id = "dimmer-i" + str(floorplan_info["instance"])
        super().__init__(floorplan_info, mqtt_support)
        self.Logger = logging.getLogger(__class__.__name__)

        # Allow MQTT to control light
        self.command_topic = mqtt_support.make_device_topic_string(
            self.id, None, False)
        self.mqtt_support.register(self.command_topic, self.process_mqtt_msg)

        # RVC message must match the following to be this device
        self.rvc_match_status = { "name": "DC_DIMMER_STATUS_3", "instance": floorplan_info['instance']}
        self.rvc_match_command= { "name": "DC_DIMMER_COMMAND_2", "instance": floorplan_info['instance']}

        self.Logger.debug(f"Must match: {str(self.rvc_match_status)} or {str(self.rvc_match_command)}")

        # save these for later to send rvc msg
        self.rvc_instance = floorplan_info['instance'] 
        self.rvc_group = '11111111'
        if 'group' in floorplan_info:
            self.rvc_group = floorplan_info['group'] 
        self.name = floorplan_info['instance_name'] 
        self.state = "unknown"
        self.messagestate = "unknown"
        self.brightness = 0

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

        if self._is_entry_match(self.rvc_match_status, new_message):
            self.Logger.debug(f"Msg Match Status: {str(new_message)}")
                   
            self.messagestate = LightSwitch_DC_DIMMER_STATUS_3.LIGHT_ON \
                if new_message["load_status"] == "01" \
                else LightSwitch_DC_DIMMER_STATUS_3.LIGHT_OFF

            # Only publish if the state has changed
            if self.messagestate != self.state or new_message["operating_status_brightness"] != self.brightness:
                # produce the HA MQTT state json
                state_json = json.dumps({"state": self.messagestate,
                        "brightness": new_message["operating_status_brightness"]})               
                self.mqtt_support.client.publish(
                    self.status_topic, state_json, retain=True)
                self.state = self.messagestate
                self.brightness = new_message["operating_status_brightness"]
            return True

        elif self._is_entry_match(self.rvc_match_command, new_message):
            # This is the command.  Just eat the message so it doesn't show up
            # as unhandled.
            self.Logger.debug(f"Msg Match Command: {str(new_message)}")
            return True
        return False

    def process_mqtt_msg(self, topic, payload, properties = None):
        self.Logger.debug(
            f"MQTT Msg Received on topic {topic} with payload {payload}")

        if topic == self.command_topic:
            json_payload = json.loads(payload)
            if json_payload["state"].lower() == LightSwitch_DC_DIMMER_STATUS_3.LIGHT_OFF:
            #If off command, only toggle off if currently on
                if self.state != LightSwitch_DC_DIMMER_STATUS_3.LIGHT_OFF:
                    self._rvc_light_toggle()
            elif "brightness" not in json_payload:
            #If on command without brightness, toggle off if already on
                 if self.state != LightSwitch_DC_DIMMER_STATUS_3.LIGHT_ON:
                    self._rvc_light_toggle()
            else:
            #If on command with brightness, set brightness
                self._rvc_change_brightness(json_payload["brightness"])
                self.Logger.debug(f"Brightness: {str(json_payload["brightness"])}")

    """
    On:
        2024-09-10 22:00:35 {'arbitration_id': '0x19fedbfd', 'data': '20FFFA05FF00FFFF', 'priority': '6', 'dgn_h': '1FE', 'dgn_l': 'DB', 'dgn': '1FEDB', 'source_id': 'FD', 'name': 'DC_DIMMER_COMMAND_2', 'instance': 32, 'group': '11111111', 'desired_level': 125.0, 'command': 5, 'command_definition': 'toggle', 'delay_duration': 255, 'interlock': '00', 'interlock_definition': 'no interlock active'}

    Off:
    2024-09-10 22:00:39 {'arbitration_id': '0x19fedbfd', 'data': '20FFFA05FF00FFFF', 'priority': '6', 'dgn_h': '1FE', 'dgn_l': 'DB', 'dgn': '1FEDB', 'source_id': 'FD', 'name': 'DC_DIMMER_COMMAND_2', 'instance': 32, 'group': '11111111', 'desired_level': 125.0, 'command': 5, 'command_definition': 'toggle', 'delay_duration': 255, 'interlock': '00', 'interlock_definition': 'no interlock active'}
    """

    def _rvc_light_toggle(self):
        #Command 5 for toggle with 250 brightness for dimmed memory value
        msg_bytes = bytearray(8)
        struct.pack_into("<BBBBBBBB", msg_bytes, 0, self.rvc_instance, int(
            self.rvc_group, 2), 250, 5, 0xFF, 0, 0xFF, 0xFF)
        self.send_queue.put({"dgn": "1FEDB", "data": msg_bytes})

    def _rvc_change_brightness(self, brightness: int):
        #Command 0 for ON with brightness scaled 0-200 (precision 0.5)
        msg_bytes = bytearray(8)
        struct.pack_into("<BBBBBBB", msg_bytes, 0, self.rvc_instance, int(
            self.rvc_group, 2), int(brightness*2), 0, 0xFF, 0, 0)
        self.send_queue.put({"dgn": "1FEDB", "data": msg_bytes})

    def initialize(self):
        # Prepare the HA auto discovery info
        config = {"name": self.name,
                  "state_topic": self.status_topic,
                  "command_topic": self.command_topic,
                  "command_on_template": '{"state": "on" {%- if brightness is defined -%}, "brightness": {{ (brightness | float / 2.55) | round(0)}} {%- endif -%}}',
                  "command_off_template": '{"state": "off"}',
                  "qos": 1, "retain": False,
                  "state_template": "{{ value_json.state }}",
                  "brightness_template": "{{ value_json.brightness | float | multiply(2.55) | round(0)}}",
                  "unique_id": self.unique_device_id,
                  "device": self.device,
                  "schema": "template"}             #VERY IMPORTANT!

        config.update(self.get_availability_discovery_info_for_ha())

        config_json = json.dumps(config)

        ha_config_topic = self.mqtt_support.make_ha_auto_discovery_config_topic(
            self.unique_device_id, "light") #This tells Home Assistant to treat this as a light

       # publish info to mqtt
        self.mqtt_support.client.publish(
            ha_config_topic, config_json, retain=True)

        # request dgn report - this should trigger that dimmer to report
        # dgn = 1FEDA which is actually  DA FE 01 <instance> FF 00 00 00
        self.Logger.debug("Sending Request for DGN")
        msg_bytes = bytearray(8)
        struct.pack_into("<BBBBBBBB", msg_bytes, 0, 0xDA,
            0xFE, 1, self.rvc_instance, 0, 0, 0, 0)

        self.send_queue.put({"dgn": "0EAFF", "data": msg_bytes})