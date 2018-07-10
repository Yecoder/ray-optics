#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2018 Michael J. Hayford
""" Top level model classes

Created on Wed Mar 14 11:08:28 2018

@author: Michael J. Hayford
"""

import os.path
import json_tricks
import codev.cmdproc as cvp

from . import sequential as seq
from . import elements as ele


def open_model(file_name):
    file_extension = os.path.splitext(file_name)[1]
    opm = None
    if file_extension == '.seq':
        opm = OpticalModel()
        cvp.read_lens(opm, file_name)
    elif file_extension == '.roa':
        with open(file_name, 'r') as f:
            obj_dict = json_tricks.load(f)
            if 'optical_model' in obj_dict:
                opm = obj_dict['optical_model']
                opm.sync_to_restore()
    return opm


class SystemSpec:
    dims = ('M', 'CM', 'MM', 'IN', 'FT')

    def __init__(self):
        self.title = ''
        self.initials = ''
        self.dimensions = 'MM'
        self.aperture_override = ''
        self.temperature = 20.0
        self.pressure = 760.0

    def nm_to_sys_units(self, nm):
        if self.dimensions == 'M':
            return 1e-9 * nm
        elif self.dimensions == 'CM':
            return 1e-7 * nm
        elif self.dimensions == 'MM':
            return 1e-6 * nm
        elif self.dimensions == 'IN':
            return 1e-6 * nm/25.4
        elif self.dimensions == 'FT':
            return 1e-6 * nm/304.8
        else:
            return nm


class OpticalModel:
    """ Top level container for optical model. """
    def __init__(self):
        self.radius_mode = False
        self.system_spec = SystemSpec()
        self.seq_model = seq.SequentialModel(self)
        self.ele_model = ele.ElementModel(self)

    def reset(self):
        rdm = self.radius_mode
        self.__init__()
        self.radius_mode = rdm

    def save_model(self, file_name):
        file_extension = os.path.splitext(file_name)[1]
        filename = file_name if len(file_extension) > 0 else file_name+'.roa'
        fs_dict = {}
        fs_dict['optical_model'] = self
        with open(filename, 'w') as f:
            json_tricks.dump(fs_dict, f, indent=1,
                             separators=(',', ':'))

    def sync_to_restore(self):
        self.seq_model.sync_to_restore(self)
        self.ele_model.sync_to_restore(self)
        self.update_model()

    def update_model(self):
        self.seq_model.update_model()
        self.ele_model.update_model()

    def nm_to_sys_units(self, nm):
        return self.system_spec.nm_to_sys_units(nm)
