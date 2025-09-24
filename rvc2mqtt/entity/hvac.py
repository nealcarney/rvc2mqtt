"""
HVAC support using Climate MQTT


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
from enum import Enum
from rvc2mqtt.mqtt import MQTT_Support
from rvc2mqtt.entity import EntityPluginBaseClass


class FanMode(Enum):
    '''
    simple class for the Fan Mode which includes Fan Modes and speed
    
    '''

    AUTO = 'auto'
    LOW  = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'

    @property
    def rvc_fan_speed_percent(self) -> int:
        if self.value == 'auto':
            return 50
        elif self.value == 'low':
            return 25
        elif self.value == 'medium':
            return 50
        elif self.value == 'high':
            return 100
        else:
            return 50
    
    @property
    def rvc_fan_speed_for_rvc_msg(self) -> int:
        return self.rvc_fan_speed_percent * 2

    @property
    def rvc_fan_mode_str(self) -> str:
        if self.value == 'auto':
            return 'auto'
        else:
            return 'on'
    
    @property
    def rvc_fan_mode_int(self) -> int:
        if self.value == 'auto':
            return 0
        else:
            return 1

    @staticmethod
    def get_fan_mode_from_rvc(speed: int, rvc_mode:str):
        if rvc_mode == 'auto':
            return FanMode.AUTO
        elif speed == 0:
            return FanMode.AUTO
        elif speed == 25:
            return FanMode.LOW
        elif speed == 50:
            return FanMode.MEDIUM
        elif speed == 100:
            return FanMode.HIGH
    
class HvacMode(Enum):
    '''
    simple class for the HVAC Mode which includes heat, cool, etc
    
    '''
    OFF = 'off'
    COOL = 'cool'
    HEAT = 'heat'                  
    DRY = 'dry'

    @property
    def rvc_mode_for_rvc_msg(self) -> str:
        if self == HvacMode.HEAT:
            return 2
        elif self == HvacMode.COOL:
            return 0                        #Needs to be 1; disabled during devlopment
        elif self == HvacMode.DRY:
           return 0                         #Needs to be 6; disabled during devlopment
        elif self == HvacMode.OFF:
            return 0
    
    @staticmethod
    def get_hvac_mode_from_rvc(rvc_mode:str):
        if rvc_mode == "fan only":
            return HvacMode.FAN_ONLY
        elif rvc_mode == "window defrost/dehumidify":
            return HvacMode.DRY
        else:
            return HvacMode(rvc_mode)


class HvacClass(EntityPluginBaseClass):
    '''
    HVAC based on climate control based on THERMOSTAT_STATUS_1 and optional temperature and furnace entities
    DGNs

    This is a multi instance device
    FLOORPLAN - Input

    type: hvac
    name: THERMOSTAT_STATUS_1
    instance_name: <friendly name>
    instance: <int>
    link_id: <str for this node> (optional, only used for linking)
    entity_links:
      - <link id of associated current temp sensor>




    HA Autodiscovery
    https://www.home-assistant.io/integrations/climate.mqtt/
        hvac
          current_temperature_topic
          current_temperature_template 

          fan_mode_command_template
          fan_mode_command_topic 
          fan_mode_state_template 
          fan_mode_state_topic 
          fan_modes 

          max_temp 
          min_temp 

          mode_command_template 
          mode_command_topic 
          mode_state_template 
          mode_state_topic 
          modes    
    ''' 

    FACTORY_MATCH_ATTRIBUTES = {"name": "THERMOSTAT_STATUS_1", "type": "hvac"}

    # HA MQTT HVAC supported modes - must be a subset of default
    MQTT_SUPPORTED_MODES = [e.value for e in HvacMode]

    MIN_TEMP = 5
    MAX_TEMP = 30

    # HA MQTT FAN supported modes - must be subset of default
    #MQTT_SUPPORTED_FAN_MODE = ["auto", "low", "medium", "high"]
    MQTT_SUPPORTED_FAN_MODE =  [e.value for e in FanMode]

    # convert rvc friendly name to rvc value
    RVC_SCHEDULE_MODE_TO_RVC_SCHEDULE_MODE_VALUE = {"disabled": 0, "enabled": 1}

    def __init__(self, floorplan_info: dict, mqtt_support: MQTT_Support):
        self.id = f"thermostat-i" + str(floorplan_info["instance"])

        super().__init__(floorplan_info, mqtt_support)
        self.Logger = logging.getLogger(__class__.__name__)

        # RVC message must match the following status or command
        self.rvc_match_status = {"name": "THERMOSTAT_STATUS_1", "instance": floorplan_info['instance']}
        self.rvc_match_command = {"name": "THERMOSTAT_COMMAND_1", "instance": floorplan_info['instance']}

        self.Logger.debug(f"Must match: {str(self.rvc_match_status)} {str(self.rvc_match_command)}")

        #Default empty objects for links
        self.temperature_entity_link = None
        self.furnace_mode_link = None
        self.furnace_action_link = None
        
        # fields for a thermostat object
        self.name = floorplan_info["instance_name"]
        self.rvc_instance = floorplan_info["instance"]
        self.scheduled_mode = "disabled"  # don't support this

        # Initial values for properties
        self._ac_mode     = HvacMode.OFF
        self._fan_mode = FanMode.AUTO
        self._set_point_temperature = 23
        # self._furnace_action = ""
        self.thermostat_action = ""
        self.thermostat_mode = HvacMode.OFF
        # self._furnace_mode = HvacMode.OFF


        self.device = {"manufacturer": "Firefly Integrations",
                       "identifiers": "Firefly",
                       "name": "Firefly",
                       "model": "G12"
                       }

        # Allow MQTT to control mode
        self.status_mode_topic = mqtt_support.make_device_topic_string(self.id, "mode", True)
        self.command_mode_topic = mqtt_support.make_device_topic_string(self.id, "mode", False)
        self.mqtt_support.register(self.command_mode_topic, self.process_mqtt_msg)

        # Allow MQTT to control fan mode
        self.status_fan_mode_topic = mqtt_support.make_device_topic_string(self.id, "fan_mode", True)
        self.command_fan_mode_topic = mqtt_support.make_device_topic_string(self.id, "fan_mode", False)
        self.mqtt_support.register(self.command_fan_mode_topic, self.process_mqtt_msg)

        # Allow MQTT to control the target temperature
        self.status_set_point_temp_topic = mqtt_support.make_device_topic_string(self.id, "set_point_temperature", True)
        self.command_set_point_temp_topic = mqtt_support.make_device_topic_string(self.id, "set_point_temperature", False)
        self.mqtt_support.register(self.command_set_point_temp_topic, self.process_mqtt_msg)

        # Provide the current action (heating, cooling, idle, off)
        self.status_action_topic = mqtt_support.make_device_topic_string(self.id, "action", True)

    @property
    def fan_mode(self) -> FanMode:
        return self._fan_mode
    @fan_mode.setter
    def fan_mode(self, value: FanMode):
        if value != self._fan_mode:
            self._fan_mode = value
            self._changed = True

    @property
    def ac_mode(self) -> HvacMode:
        return self._ac_mode
    @ac_mode.setter
    def ac_mode(self, value: HvacMode):
        if value != self._ac_mode:
            self._ac_mode = value
            self.update_thermostat_mode()
            self._changed = True

    @property
    def set_point_temperature(self) -> float:
        return self._set_point_temperature
    @set_point_temperature.setter
    def set_point_temperature(self, value: float):
        if value != self._set_point_temperature:
            self._set_point_temperature = value
            self._changed = True
    
    # @property
    # def furnace_action(self) -> str:
    #     return self._furnace_action
    # @furnace_action.setter
    # def furnace_action(self, value: str):
    #     #This property gets set by the furnace action entity link
    #     self.Logger.debug(f"Received update of heat action: {value}") 
    #     if value != self._furnace_action:
    #         #Notify overall action_changed tracker about change
    #         self.Logger.debug(f"Updating thermostat with heat action: {value}")
    #         self._furnace_action = value
    #         self.update_thermostat_action()
   
    # @property
    # def furnace_mode(self) -> str:
    #     return self._furnace_mode
    # @furnace_mode.setter
    # def furnace_mode(self, value: str):
    #     #This property gets set by the furnace mode entity link
    #     self.Logger.debug(f"Received update of furnace mode: {value}") 
    #     if value != self._furnace_mode:
    #         #Notify overall action_changed tracker about change
    #         self.Logger.debug(f"Updating thermostat with furnace mode: {value}")
    #         self._furnace_mode = value
            #self.update_thermostat_mode()

    def update_thermostat_action(self):
        ''' Update the thermostat action based on furnace action and modes'''
        self.Logger.info(f"Evaluating thermostat action  {self.ac_mode} {self.furnace_mode_link.mode.value}\r\n")
        self.thermostat_action = "off"
        if self.ac_mode == HvacMode.OFF and self.furnace_mode_link.mode.value == "off":
            self.thermostat_action = "off"
        elif self.furnace_action_link is not None:
            if self.furnace_action_link.action in ["heating", "cooling"]:
                self.thermostat_action = self.furnace_action_link.action
            else:
                self.thermostat_action = "idle"
        self.Logger.debug(f"Updating MQTT with action: { self.thermostat_action}")
        self.mqtt_support.client.publish(self.status_action_topic, self.thermostat_action, retain=True)

    def update_thermostat_mode(self):
        ''' Update the thermostat mode based on furnace mode'''
        self.Logger.info(f"Evaluating thermostat mode  {self.ac_mode} {self.furnace_mode_link.mode.value}\r\n")
        if self.ac_mode == HvacMode.OFF and self.furnace_mode_link.mode.value == "off":
            self.thermostat_mode = HvacMode.OFF
        elif self.furnace_mode_link.mode.value == "heat":
            self.thermostat_mode = HvacMode.HEAT
        else:
            self.thermostat_mode = self.ac_mode
        self.Logger.info(f"Updating MQTT with mode: { self.thermostat_mode.value}")
        self.mqtt_support.client.publish(self.status_mode_topic, self.thermostat_mode.value, retain=True)

    def add_entity_link(self, obj):
        """ optional function
        If the data of the object has an entity_links list this function 
        will get called with each entity"""
        
        self.Logger.debug(f"Adding entities")
        if obj.link_id == "temperature":
            self.Logger.debug(f"Linking to {obj.name}")
            self.temperature_entity_link = obj
        elif obj.link_id == "furnace-mode":
            self.Logger.debug(f"Linking to {obj.name}")
            self.furnace_mode_link = obj
            #Two way link so furnace mode can update this entity
            obj.thermostat_entity_link = self
        elif obj.link_id == "furnace-action":
            self.Logger.debug(f"Linking to {obj.name}")
            self.furnace_action_link = obj
            #Two way link so furnace action can update this entity
            obj.thermostat_entity_link = self
        else:
            self.Logger.error(f"Unknown entity link {obj.name}")

    def process_rvc_msg(self, new_message: dict) -> bool:
        """ Process an incoming message and determine if it
        is of interest to this object.

        If relevant - Process the message and return True
        else - return False

        Message looks like:

        
            RV-C message for THERMOSTAT_STATUS_1

        {'arbitration_id': '0x19ffe259', 'data': '02000060246024FF', 'priority': '6', 'dgn_h': '1FF', 'dgn_l': 'E2', 'dgn': '1FFE2',
            'source_id': '59', 'name': 'THERMOSTAT_STATUS_1', 'instance': 2,
            'operating_mode': '0000', 'operating_mode_definition': False,
            'fan_mode': '00', 'fan_mode_definition': 'auto',
            'schedule_mode': '00', 'schedule_mode_definition': 'disabled',
            'fan_speed': 0.0,
            'setpoint_temp_heat': 18.0,
            'setpoint_temp_cool': 18.0}

        """


        if self._is_entry_match(self.rvc_match_status, new_message):
            self.Logger.debug(f"Msg Match Status: {str(new_message)}")

            self.fan_mode = FanMode.get_fan_mode_from_rvc(int(new_message["fan_speed"]), new_message["fan_mode_definition"] )
            # use cool because for this implementation we will update cool and heat to the same value
            self.set_point_temperature = new_message["setpoint_temp_cool"]
            if new_message["setpoint_temp_cool"] != new_message["setpoint_temp_heat"]:
                self.Logger.debug(f"Expected cool and heat set temperatures to always be the same.  They are not")
            self.ac_mode = HvacMode.get_hvac_mode_from_rvc(new_message["operating_mode_definition"])
            self._update_mqtt_topics_with_changed_values()
            return True
        elif self._is_entry_match(self.rvc_match_command, new_message):
            self.Logger.debug(f"Msg Match Command: {str(new_message)}")
            # do nothing from command
        return False

    def _update_mqtt_topics_with_changed_values(self):
        ''' entry data has potentially changed.  Update mqtt'''

        if self._changed: 
            #self.mqtt_support.client.publish(self.status_mode_topic, self.ac_mode.value, retain=True)
            self.mqtt_support.client.publish(self.status_fan_mode_topic, self.fan_mode.value, retain=True)
            self.mqtt_support.client.publish(self.status_set_point_temp_topic, self.set_point_temperature, retain=True)
            self._changed = False
        return False

    def _convert_temp_c_to_rvc_uint16(self, temp_c: float):
        ''' convert a temperature stored in C to a UINT16 value for RVC'''
        return round((temp_c + 273 ) * 32)

    def _make_rvc_payload(self, instance:int, mode:HvacMode, fan_mode:FanMode, schedule_mode:str, temperature_c:float):
        ''' Make 8 byte buffer in THERMOSTAT_COMMAND_1 format. 
        
        {   'arbitration_id': '0x19fef944', 'data': '0200645824582400',
            'priority': '6', 'dgn_h': '1FE', 'dgn_l': 'F9', 'dgn': '1FEF9',
            'source_id': '44',
            'name': 'THERMOSTAT_COMMAND_1',
            'instance': 2,
            'operating_mode': '0000', 'operating_mode_definition': 'off',
            'fan_mode': '00', 'fan_mode_definition': 'auto',
            'schedule_mode': '00', 'schedule_mode_definition': 'disabled',
            'fan_speed': 50.0, 
            'setpoint_temp_heat': 17.75, 'setpoint_temp_cool': 17.75}
         '''
        msg_bytes = bytearray(8)
        mi = mode.rvc_mode_for_rvc_msg
        fmi = fan_mode.rvc_fan_mode_int
        smi = HvacClass.RVC_SCHEDULE_MODE_TO_RVC_SCHEDULE_MODE_VALUE[schedule_mode]  # schedule mode int value
        fsi = fan_mode.rvc_fan_speed_for_rvc_msg
        temperature_uint16 = self._convert_temp_c_to_rvc_uint16(temperature_c)

        struct.pack_into("<BBBHHB", msg_bytes, 0, instance, (mi | (fmi << 4) | (smi << 6)), fsi, temperature_uint16, temperature_uint16, 0  )
        return msg_bytes


    def process_mqtt_msg(self, topic, payload):
        """ Read mqtt incoming command message

            convert the new value into entity format
            make an rvc command message with the new value 
            queue it
               
        """
        self.Logger.debug(f"MQTT Msg Received on topic {topic} with payload {payload}")

        if topic == self.command_mode_topic:
            try:
                mode = HvacMode(payload.lower())
                self.Logger.debug(f"Mode requested to be changed to {mode}")
                if self.furnace_mode_link is not None:
                    self.furnace_mode_link.process_mqtt_msg(payload)
                # Temporarily disabled during development until ready to process AC commands
                # Need to turn one on and the other off to switch between heat and cool
                # pl = self._make_rvc_payload(self.rvc_instance, mode, self.fan_mode, self.scheduled_mode, self.set_point_temperature)
                # self.send_queue.put({"dgn": "1FEF9", "data": pl})
            except Exception as e:
                self.Logger.error(f"Exception trying to respond to topic {topic} + {str(e)}")

        elif topic == self.command_fan_mode_topic:
            try: 
                fan_mode = FanMode(payload)
                pl = self._make_rvc_payload(self.rvc_instance, self.ac_mode, fan_mode, self.scheduled_mode, self.set_point_temperature)
                self.send_queue.put({"dgn": "1FEF9", "data": pl})
            except Exception as e:
                self.Logger.error(f"Exception trying to respond to topic {topic} + {str(e)}")

        elif topic == self.command_set_point_temp_topic:
            try: 
                # temp = float(payload)
                # pl = self._make_rvc_payload(self.rvc_instance, self.ac_mode, self.fan_mode, self.scheduled_mode, temp)
                msg_bytes = bytearray(8)
                mi = 15 #1111
                fmi = 3 #11
                smi = 3 #11
                fsi = 255
                temp = self._convert_temp_c_to_rvc_uint16(float(payload))
                ### Hard coded instance 3 for testing
                pl = struct.pack_into("<BBBHHB", msg_bytes, 0, 3, (mi | (fmi << 4) | (smi << 6)), fsi, 65535, temp, 0  )
                self.send_queue.put({"dgn": "1FEF9", "data": msg_bytes})
            except Exception as e:
                self.Logger.error(f"Exception trying to respond to topic {topic} + {str(e)}")

        else:
            self.Logger.error(f"Invalid payload {payload} for topic {topic}")

    def initialize(self):
        """ Optional function 
        Will get called once when the object is loaded.  
        RVC canbus tx queue is available
        mqtt client is ready.  

        This can be a good place to request data

        """

        self.Logger.debug(f"Setting up autodiscovery for: {self.name}")
        config = {"name": self.name,
                    "modes": HvacClass.MQTT_SUPPORTED_MODES,
                    "mode_state_topic": self.status_mode_topic,
                    "mode_state_template": '{{value}}',
                    "mode_command_topic": self.command_mode_topic,
                    "mode_command_template": '{{value}}',

                    "action_topic": self.status_action_topic,
                    "action_template": '{{value}}',

                    "temperature_unit": 'C',
                    "min_temp": HvacClass.MIN_TEMP,
                    "max_temp": HvacClass.MAX_TEMP,
                    "precision": 1,

                    "fan_modes": HvacClass.MQTT_SUPPORTED_FAN_MODE,
                    "fan_mode_state_topic": self.status_fan_mode_topic,
                    "fan_mode_state_template": '{{value}}',
                    "fan_mode_command_topic": self.command_fan_mode_topic,
                    "fan_mode_command_template": '{{value}}',

                    "temperature_state_topic": self.status_set_point_temp_topic,
                    "temperature_state_template": '{{value}}',
                    "temperature_command_topic": self.command_set_point_temp_topic,
                    "temperature_command_template": '{{value}}',
                    
                    "qos": 1, "retain": False,
                    "unique_id": self.unique_device_id,
                    "device": self.device}

        if self.temperature_entity_link is not None:
            config["current_temperature_topic"] = self.temperature_entity_link.status_topic
            config["current_temperature_template"] = '{{value}}'

        config.update(self.get_availability_discovery_info_for_ha())

        config_json = json.dumps(config)

        ha_config_topic = self.mqtt_support.make_ha_auto_discovery_config_topic(
            self.unique_device_id, "climate")

        # publish info to mqtt
        self.Logger.debug(f"Publishing: {self.name}")
        self.mqtt_support.client.publish(
            ha_config_topic, config_json, retain=True)

        self.update_thermostat_action