# Support for OAMS ACE mainboard
#
# Copyright (C) 2024 JR Lomas <lomas.jr@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import mcu
import struct

OAMS_STATUS_LOADING = 0
OAMS_STATUS_UNLOADING = 1
OAMS_STATUS_FORWARD_FOLLOWING = 2
OAMS_STATUS_REVERSE_FOLLOWING = 3
OAMS_STATUS_COASTING = 4
OAMS_STATUS_STOPPED = 5
OAMS_STATUS_CALIBRATING = 6

OAMS_OP_CODE_SUCCESS = 0
OAMS_OP_CODE_ERROR_UNSPECIFIED = 1
OAMS_OP_CODE_ERROR_BUSY = 2

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
        self.name = config.get_name()
        # 
        # self.mcu.register_response(
        #     self._oams_status, "oams_status", self.oid
        # )
        # self.oid = self.mcu.create_oid()
        
        self.mcu.register_response(
            self._oams_action_status, "oams_action_status"
        )
        self.mcu.register_config_callback(self._build_config)
        self.name = config.get_name()
        #logging.info("mcu commands: %s", self.mcu.get_commands())
        self.register_commands(self.name)
        self.printer.add_object("oams", self)
        self.reactor = self.printer.get_reactor()
        self.action_status = None
        self.action_status_code = None
        
        super().__init__()
        
    def register_commands(self, name):
        # Register commands
        gcode = self.printer.lookup_object("gcode")
        gcode.register_command ("OAMS_LOAD_SPOOL",
            self.cmd_OAMS_LOAD_SPOOL,
            desc=self.cmd_OAMS_LOAD_SPOOL_help,
        )
        gcode.register_command("OAMS_UNLOAD_SPOOL",
            self.cmd_OAMS_UNLOAD_SPOOL,
            self.cmd_OAMS_UNLOAD_SPOOL_help)
        
        gcode.register_command("OAMS_FOLLOWER",
            self.cmd_OAMS_FOLLOWER,
            self.cmd_OAMS_ENABLE_FOLLOWER_help)
        
        gcode.register_command("OAMS_CALIBRATE_PTFE_LENGTH",
            self.cmd_OAMS_CALIBRATE_PTFE_LENGTH,
            self.cmd_OAMS_CALIBRATE_PTFE_LENGTH_help)
        
        gcode.register_command("OAMS_CALIBRATE_HUB_HES",
            self.cmd_OAMS_CALIBRATE_HUB_HES,
            self.cmd_OAMS_CALIBRATE_HUB_HES_help)
        
    cmd_OAMS_CALIBRATE_HUB_HES_help = "Calibrate the range of a single hub HES"
    def cmd_OAMS_CALIBRATE_HUB_HES(self, gcmd):
        self.action_status = OAMS_STATUS_CALIBRATING
        spool_idx = gcmd.get_int("SPOOL", None)
        if spool_idx is None:
            raise gcmd.error("SPOOL index is required")
        if spool_idx < 0 or spool_idx > 3:
            raise gcmd.error("Invalid SPOOL index")
        self.oams_calibrate_hub_hes_cmd.send([spool_idx])
        while(self.action_status is not None):
            self.reactor.pause(self.reactor.monotonic() + 0.1)
        if self.action_status_code == OAMS_OP_CODE_SUCCESS:
            gcmd.respond_info("Calibrated HES %d to %d threshold" % (spool_idx, self.action_status_value))
            # configfile = self.printer.lookup_object('configfile')
            # configfile.set(self.name, 'ptfe_length', "%d" % (self.action_status_value,))
            # gcmd.respond_info("Done calibrating clicks, output saved to configuration")
        else:
            gcmd.respond_error("Calibration of HES %d failed" % spool_idx)
        
    cmd_OAMS_CALIBRATE_PTFE_LENGTH_help = "Calibrate the length of the PTFE tube"
    def cmd_OAMS_CALIBRATE_PTFE_LENGTH(self, gcmd):
        self.action_status = OAMS_STATUS_CALIBRATING
        spool = gcmd.get_int("SPOOL", None)
        if spool is None:
            raise gcmd.error("SPOOL index is required")
        self.oams_calibrate_ptfe_length_cmd.send([spool])
        while(self.action_status is not None):
            self.reactor.pause(self.reactor.monotonic() + 0.1)
        if self.action_status_code == OAMS_OP_CODE_SUCCESS:
            gcmd.respond_info("Calibrated PTFE length to %d" % self.action_status_value)
            configfile = self.printer.lookup_object('configfile')
            configfile.set(self.name, 'ptfe_length', "%d" % (self.action_status_value,))
            gcmd.respond_info("Done calibrating clicks, output saved to configuration")
        else:
            gcmd.respond_error("Calibration of PTFE length failed")
    
    cmd_OAMS_LOAD_SPOOL_help = "Load a new spool of filament"
    def cmd_OAMS_LOAD_SPOOL(self, gcmd):
        self.action_status = OAMS_STATUS_LOADING
        spool_idx = gcmd.get_int("SPOOL", None)
        if spool_idx is None:
            raise gcmd.error("SPOOL index is required")
        if spool_idx < 0 or spool_idx > 3:
             raise gcmd.error("Invalid SPOOL index")
        self.oams_load_spool_cmd.send([spool_idx])
        # we now want to wait until we get a response from the MCU
        while(self.action_status is not None):
            self.reactor.pause(self.reactor.monotonic() + 0.1)
        
        if self.action_status_code == OAMS_OP_CODE_SUCCESS:
            gcmd.respond_info("Spool unloaded successfully")
        elif self.action_status_code == OAMS_OP_CODE_ERROR_BUSY:
            gcmd.respond_error("OAMS is busy")
        else:    
            gcmd.respond_error("Unknown error from OAMS")

        
    cmd_OAMS_UNLOAD_SPOOL_help = "Unload a spool of filament"
    def cmd_OAMS_UNLOAD_SPOOL(self, gcmd):
        self.action_status = OAMS_STATUS_UNLOADING
        self.oams_unload_spool_cmd.send()
        while(self.action_status is not None):
            self.reactor.pause(self.reactor.monotonic() + 0.1)
        if self.action_status_code == OAMS_OP_CODE_SUCCESS:
            gcmd.respond_info("Spool unloaded successfully")
        elif self.action_status_code == OAMS_OP_CODE_ERROR_BUSY:
            gcmd.respond_error("OAMS is busy")
        else:    
            gcmd.respond_error("Unknown error from OAMS")
            
    cmd_OAMS_ENABLE_FOLLOWER_help = "Enable the follower"
    def cmd_OAMS_FOLLOWER(self, gcmd):
        enable = gcmd.get_int("ENABLE", None)
        if enable is None:
            raise gcmd.error("ENABLE is required")
        direction = gcmd.get_int("DIRECTION", None)
        if direction is None:
            raise gcmd.error("DIRECTION is required")
        self.oams_follower_cmd.send([enable, direction])
        if enable == 1 and direction == 0:
            gcmd.respond_info("Follower enable in forward direction")
        elif enable == 1 and direction == 1:
            gcmd.respond_info("Follower enable in reverse direction")
        elif enable == 0:
            gcmd.respond_info("Follower disabled")


    def _oams_action_status(self,params):
        logging.info("oams status received")
        if params['action'] == OAMS_STATUS_LOADING:
            self.action_status = None
            self.action_status_code = params['code']
        elif params['action'] == OAMS_STATUS_UNLOADING:
            self.action_status = None
            self.action_status_code = params['code']
        elif params['action'] == OAMS_STATUS_CALIBRATING:
            self.action_status = None
            self.action_status_code = params['code']
            self.action_status_value = params['value']
        else:
            logging.error("Spurious response from AMS with code %d and action %d", params['code'], params['action'])

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
        
        self.oams_load_spool_cmd = self.mcu.lookup_command(
            "oams_cmd_load_spool spool=%c"
        )
        
        self.oams_unload_spool_cmd = self.mcu.lookup_command(
            "oams_cmd_unload_spool"
        )
        
        self.oams_follower_cmd = self.mcu.lookup_command(
            "oams_cmd_follower enable=%c direction=%c"
        )
        
        self.oams_calibrate_ptfe_length_cmd = self.mcu.lookup_command(
            "oams_cmd_calibrate_ptfe_length spool=%c"
        )
        
        self.oams_calibrate_hub_hes_cmd = self.mcu.lookup_command(
            "oams_cmd_calibrate_hub_hes spool=%c"
        )

    def get_status(self, eventtime):
        return {
            "placeholder": "ok?",
        }


def load_config_prefix(config):
    return OAMS(config)

def load_config(config):
    return OAMS(config)
