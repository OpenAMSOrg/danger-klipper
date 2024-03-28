# Support for OAMS ACE mainboard
#
# Copyright (C) 2024 JR Lomas <lomas.jr@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import mcu
import struct

class OAMS:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name()
        self.mcu = mcu.get_printer_mcu(self.printer, config.get("mcu", "mcu"))
        self.fps_upper_threshold = config.getfloat("fps_upper_threshold")
        self.fps_lower_threshold = config.getfloat("fps_lower_threshold")
        self.fps_is_reversed = config.getboolean("fps_is_reversed")
        self.f1s_hes_on = list(map(lambda x: float(x.strip()), config.get("f1s_hes_on").split(",")))
        self.f1s_hes_is_above = config.getboolean("f1s_hes_is_above")
        self.hub_hes_on = list(map(lambda x: float(x.strip()), config.get("hub_hes_on").split(",")))
        self.hub_hes_is_above = config.getboolean("hub_hes_is_above")
        self.filament_path_length = config.getfloat("ptfe_length")
        self.oid = self.mcu.create_oid()
        self.mcu.register_response(
            self._oams_status, "oams_status", self.oid
        )
        self.mcu.register_config_callback(self._build_config)
        self.printer.add_object('oams', self)
        
        super().__init__()

    def _oams_status(self,params):
        logging.info("oams status received")

    def float_to_u32(self, f):
        return struct.unpack('I', struct.pack('f', f))[0]


    def _build_config(self):
        self.mcu.add_config_cmd(
            "config_oams_buffer upper=%u lower=%u is_reversed=%u"
            % (
                self.float_to_u32(self.fps_upper_threshold), 
                self.float_to_u32(self.fps_lower_threshold), 
                self.float_to_u32(self.fps_is_reversed)
            )
        )

        self.mcu.add_config_cmd(
            "config_oams_f1s_hes on1=%u on2=%u on3=%u on4=%u is_above=%u"
            % ( 
                self.float_to_u32(self.f1s_hes_on[0]),
                self.float_to_u32(self.f1s_hes_on[1]),
                self.float_to_u32(self.f1s_hes_on[2]),
                self.float_to_u32(self.f1s_hes_on[3]),
                self.f1s_hes_is_above
            )
        )

        self.mcu.add_config_cmd(
            "config_oams_hub_hes on1=%u on2=%u on3=%u on4=%u is_above=%u"
            % ( 
                self.float_to_u32(self.hub_hes_on[0]),
                self.float_to_u32(self.hub_hes_on[1]),
                self.float_to_u32(self.hub_hes_on[2]),
                self.float_to_u32(self.hub_hes_on[3]),
                self.hub_hes_is_above
            )
        )

        self.mcu.add_config_cmd(
            "config_oams_ptfe length=%u"
            % (self.filament_path_length)
        )

    def get_status(self, eventtime):
        return {
            "placeholder": "ok?",
        }


def load_config_prefix(config):
    return OAMS(config)

def load_config(config):
    return OAMS(config)
