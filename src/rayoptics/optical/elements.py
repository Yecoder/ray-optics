#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2018 Michael J. Hayford
""" Module for element modeling

.. Created on Sun Jan 28 16:27:01 2018

.. codeauthor: Michael J. Hayford
"""

import logging
from collections import namedtuple

import math
import numpy as np

import rayoptics.util.rgbtable as rgbt
import rayoptics.optical.thinlens as thinlens
from rayoptics.optical.profiles import Spherical, Conic
from rayoptics.optical.surface import Surface
from rayoptics.optical.gap import Gap
from rayoptics.gui.actions import Action, AttrAction, SagAction, BendAction
from rayoptics.optical.medium import Glass, glass_decode
import opticalglass.glasspolygons as gp

GraphicsHandle = namedtuple('GraphicsHandle', ['polydata', 'tfrm', 'polytype'])
""" tuple grouping together graphics rendering data

    Attributes:
        polydata: poly data in local coordinates
        tfrm: global transformation for polydata
        polytype: 'polygon' (for filled) or 'polyline'
"""


def create_thinlens(power=0., indx=1.5):
    tl = thinlens.ThinLens(power=power)
    tle = ThinElement(tl)
    return tl, tle


def create_mirror(c=0.0, r=None, cc=0.0, ec=None):
    if r:
        cv = 1.0/r
    else:
        cv = c

    if ec:
        k = ec - 1.0
    else:
        k = cc

    if k == 0.0:
        profile = Spherical(c=cv)
    else:
        profile = Conic(c=cv, cc=k)

    m = Surface(profile=profile, refract_mode='REFL')
    me = Mirror(m)
    return m, me


def create_lens(power=0., bending=0., th=0., sd=1., med=None):
    s1 = Surface()
    s2 = Surface()
    if med is None:
        med = Glass()
    g = Gap(t=th, med=med)
    le = Element(s1, s2, g, sd=sd)
    return (s1, s2, g), le


def create_dummy_plane(sd=1.):
    s = Surface()
    se = DummyInterface(s, sd=sd)
    return s, se


class Element():
    clut = rgbt.RGBTable(filename='red_blue64.csv',
                         data_range=[10.0, 100.])

    label_format = 'E{}'

    def __init__(self, s1, s2, g, tfrm=None, idx=0, idx2=1, sd=1.,
                 label='Lens'):
        self.label = label
        if tfrm is not None:
            self.tfrm = tfrm
        else:
            self.trfm = (np.identity(3), np.array([0., 0., 0.]))
        self.s1 = s1
        self.s1_indx = idx
        self.s2 = s2
        self.s2_indx = idx2
        self.g = g
        self._sd = sd
        self.flat1 = None
        self.flat2 = None
        self.render_color = self.calc_render_color()

    @property
    def sd(self):
        return self._sd

    @sd.setter
    def sd(self, semidiam):
        self._sd = semidiam
        self.edge_extent = (-semidiam, semidiam)

    def __json_encode__(self):
        attrs = dict(vars(self))
        del attrs['parent']
        del attrs['tfrm']
        del attrs['s1']
        del attrs['s2']
        del attrs['g']
        del attrs['handles']
        del attrs['actions']
        return attrs

    def __str__(self):
        fmt = 'Element: {!r}, {!r}, t={:.4f}, sd={:.4f}, glass: {}'
        return fmt.format(self.s1.profile, self.s2.profile, self.g.thi,
                          self.sd, self.g.medium.name())

    def sync_to_restore(self, ele_model, surfs, gaps, tfrms):
        # when restoring, we want to use the stored indices to look up the
        # new object instances
        self.parent = ele_model
        self.tfrm = tfrms[self.s1_indx]
        self.s1 = surfs[self.s1_indx]
        self.g = gaps[self.s1_indx]
        self.s2 = surfs[self.s2_indx]

    def sync_to_update(self, seq_model):
        # when updating, we want to use the stored object instances to get the
        # current indices into the interface list (e.g. to handle insertion and
        # deletion of interfaces)
        self.s1_indx = seq_model.ifcs.index(self.s1)
        self.s2_indx = seq_model.ifcs.index(self.s2)
        self.render_color = self.calc_render_color()

    def reference_interface(self):
        return self.s1

    def get_bending(self):
        cv1 = self.s1.profile_cv
        cv2 = self.s2.profile_cv
        delta_cv = cv1 - cv2
        bending = 0.
        if delta_cv != 0.0:
            bending = (cv1 + cv2)/delta_cv
        return bending

    def set_bending(self, bending):
        cv1 = self.s1.profile_cv
        cv2 = self.s2.profile_cv
        delta_cv = cv1 - cv2
        cv2_new = 0.5*(bending - 1.)*delta_cv
        cv1_new = bending*delta_cv - cv2_new
        self.s1.profile_cv = cv1_new
        self.s2.profile_cv = cv2_new

    def update_size(self):
        extents = np.union1d(self.s1.get_y_aperture_extent(),
                             self.s2.get_y_aperture_extent())
        self.edge_extent = (extents[0], extents[-1])
        self.sd = max(self.s1.surface_od(), self.s2.surface_od())
        return self.sd

    def calc_render_color(self):
        try:
            gc = float(self.g.medium.glass_code())
        except AttributeError:
            return (255, 255, 255)  # white
        else:
            # set element color based on V-number
            indx, vnbr = glass_decode(gc)
            dsg, rgb = gp.find_glass_designation(indx, vnbr)
#            rgb = Element.clut.get_color(vnbr)
            return rgb

    def compute_flat(self, s):
        ca = s.surface_od()
        if (1.0 - ca/self.sd) >= 0.05:
            flat = ca
        else:
            flat = None
        return flat

    def extent(self):
        if hasattr(self, 'edge_extent'):
            return self.edge_extent
        else:
            return (-self.sd, self.sd)

    def render_shape(self):
        if self.s1.profile_cv < 0.0:
            self.flat1 = self.compute_flat(self.s1)
        poly = self.s1.full_profile(self.extent(), self.flat1)
        if self.s2.profile_cv > 0.0:
            self.flat2 = self.compute_flat(self.s2)
        poly2 = self.s2.full_profile(self.extent(), self.flat2, -1)
        for p in poly2:
            p[0] += self.g.thi
        poly += poly2
        poly.append(poly[0])
        return poly

    def render_handles(self, opt_model):
        self.handles = {}
        ifcs_gbl_tfrms = opt_model.seq_model.gbl_tfrms

        shape = self.render_shape()
        self.handles['shape'] = GraphicsHandle(shape, self.tfrm, 'polygon')

        extent = self.extent()
        if self.flat1 is not None:
            extent_s1 = self.flat1,
        else:
            extent_s1 = extent
        poly_s1 = self.s1.full_profile(extent_s1, None)
        gh1 = GraphicsHandle(poly_s1, ifcs_gbl_tfrms[self.s1_indx], 'polyline')
        self.handles['s1_profile'] = gh1

        if self.flat2 is not None:
            extent_s2 = self.flat2,
        else:
            extent_s2 = extent
        poly_s2 = self.s2.full_profile(extent_s2, None, -1)
        gh2 = GraphicsHandle(poly_s2, ifcs_gbl_tfrms[self.s2_indx], 'polyline')
        self.handles['s2_profile'] = gh2

        poly_sd_upr = []
        poly_sd_upr.append([poly_s1[-1][0], extent[1]])
        poly_sd_upr.append([poly_s2[0][0]+self.g.thi, extent[1]])
        self.handles['sd_upr'] = GraphicsHandle(poly_sd_upr, self.tfrm,
                                                'polyline')

        poly_sd_lwr = []
        poly_sd_lwr.append([poly_s2[-1][0]+self.g.thi, extent[0]])
        poly_sd_lwr.append([poly_s1[0][0], extent[0]])
        self.handles['sd_lwr'] = GraphicsHandle(poly_sd_lwr, self.tfrm,
                                                'polyline')

        poly_ct = []
        poly_ct.append([0., 0.])
        poly_ct.append([self.g.thi, 0.])
        self.handles['ct'] = GraphicsHandle(poly_ct, self.tfrm, 'polyline')

        return self.handles

    def handle_actions(self):
        self.actions = {}

        shape_actions = {}
        shape_actions['pt'] = BendAction(self)
        shape_actions['y'] = AttrAction(self, 'sd')
        self.actions['shape'] = shape_actions

        s1_prof_actions = {}
        s1_prof_actions['pt'] = SagAction(self.s1)
        self.actions['s1_profile'] = s1_prof_actions

        s2_prof_actions = {}
        s2_prof_actions['pt'] = SagAction(self.s2)
        self.actions['s2_profile'] = s2_prof_actions

        sd_upr_action = {}
        sd_upr_action['y'] = AttrAction(self, 'sd')
        self.actions['sd_upr'] = sd_upr_action

        sd_lwr_action = {}
        sd_lwr_action['y'] = AttrAction(self, 'sd')
        self.actions['sd_lwr'] = sd_lwr_action

        ct_action = {}
        ct_action['x'] = AttrAction(self.g, 'thi')
        self.actions['ct'] = ct_action

        return self.actions


class Mirror():

    label_format = 'M{}'

    def __init__(self, ifc, tfrm=None, idx=0, sd=1., thi=None, z_dir=1.0,
                 label='Mirror'):
        self.label = label
#        self.render_color = (192, 192, 192, 112)
        self.render_color = (158, 158, 158, 64)
#        self.render_color = (64, 64, 64, 64)
        if tfrm is not None:
            self.tfrm = tfrm
        else:
            self.trfm = (np.identity(3), np.array([0., 0., 0.]))
        self.s = ifc
        self.s_indx = idx
        self.z_dir = z_dir
        self.sd = sd
        self.flat = None
        self.thi = thi

    def get_thi(self):
        thi = self.thi
        if self.thi is None:
            thi = 0.05*self.sd
        return thi

    def __json_encode__(self):
        attrs = dict(vars(self))
        del attrs['parent']
        del attrs['tfrm']
        del attrs['s']
        del attrs['handles']
        del attrs['actions']
        return attrs

    def __str__(self):
        thi = self.get_thi()
        fmt = 'Mirror: {!r}, t={:.4f}, sd={:.4f}'
        return fmt.format(self.s.profile, thi, self.sd)

    def sync_to_restore(self, ele_model, surfs, gaps, tfrms):
        self.parent = ele_model
        self.tfrm = tfrms[self.s_indx]
        self.s = surfs[self.s_indx]

    def reference_interface(self):
        return self.s

    def sync_to_update(self, seq_model):
        self.s_indx = seq_model.ifcs.index(self.s)

    def update_size(self):
        self.edge_extent = self.s.get_y_aperture_extent()
        self.sd = self.s.surface_od()
        return self.sd

    def extent(self):
        if hasattr(self, 'edge_extent'):
            return self.edge_extent
        else:
            self.edge_extent = self.s.get_y_aperture_extent()
            return self.edge_extent

    def render_shape(self):
        poly = self.s.full_profile(self.extent(), self.flat)
        poly2 = self.s.full_profile(self.extent(), self.flat, -1)

        thi = self.get_thi()
        offset = thi*self.z_dir

        for p in poly2:
            p[0] += offset
        poly += poly2
        poly.append(poly[0])
        return poly

    def render_handles(self, opt_model):
        self.handles = {}
        ifcs_gbl_tfrms = opt_model.seq_model.gbl_tfrms

        self.handles['shape'] = GraphicsHandle(self.render_shape(), self.tfrm,
                                               'polygon')

        poly = self.s.full_profile(self.extent(), None)
        self.handles['s_profile'] = GraphicsHandle(poly,
                                                   ifcs_gbl_tfrms[self.s_indx],
                                                   'polyline')

        thi = self.get_thi()
        offset = thi*self.z_dir

        poly_sd_upr = []
        poly_sd_upr.append(poly[-1])
        poly_sd_upr.append([poly[-1][0]+offset, poly[-1][1]])
        self.handles['sd_upr'] = GraphicsHandle(poly_sd_upr, self.tfrm,
                                                'polyline')

        poly_sd_lwr = []
        poly_sd_lwr.append(poly[0])
        poly_sd_lwr.append([poly[0][0]+offset, poly[0][1]])
        self.handles['sd_lwr'] = GraphicsHandle(poly_sd_lwr, self.tfrm,
                                                'polyline')

        return self.handles

    def handle_actions(self):
        self.actions = {}

        shape_actions = {}
        shape_actions['pt'] = SagAction(self.s)
        self.actions['shape'] = shape_actions

        s_prof_actions = {}
        s_prof_actions['pt'] = SagAction(self.s)
        self.actions['s_profile'] = s_prof_actions

        sd_upr_action = {}
        sd_upr_action['y'] = AttrAction(self, 'edge_extent[1]')
        self.actions['sd_upr'] = sd_upr_action

        sd_lwr_action = {}
        sd_lwr_action['y'] = AttrAction(self, 'edge_extent[0]')
        self.actions['sd_lwr'] = sd_lwr_action

        return self.actions


class ThinElement():

    label_format = 'TL{}'

    def __init__(self, ifc, tfrm=None, idx=0, label='ThinLens'):
        self.label = label
        self.render_color = (192, 192, 192)
        if tfrm is not None:
            self.tfrm = tfrm
        else:
            self.trfm = (np.identity(3), np.array([0., 0., 0.]))
        self.intrfc = ifc
        self.intrfc_indx = idx
        self.sd = ifc.od

    def __json_encode__(self):
        attrs = dict(vars(self))
        del attrs['parent']
        del attrs['tfrm']
        del attrs['intrfc']
        del attrs['handles']
        del attrs['actions']
        return attrs

    def __str__(self):
        return str(self.intrfc)

    def sync_to_restore(self, ele_model, surfs, gaps, tfrms):
        self.parent = ele_model
        self.tfrm = tfrms[self.intrfc_indx]
        self.intrfc = surfs[self.intrfc_indx]

    def reference_interface(self):
        return self.intrfc

    def sync_to_update(self, seq_model):
        self.intrfc_indx = seq_model.ifcs.index(self.intrfc)

    def update_size(self):
        self.sd = self.intrfc.surface_od()
        return self.sd

    def render_shape(self):
        poly = self.intrfc.full_profile((-self.sd, self.sd))
        return poly

    def render_handles(self, opt_model):
        self.handles = {}
        shape = self.render_shape()
        self.handles['shape'] = GraphicsHandle(shape, self.tfrm, 'polygon')
        return self.handles

    def handle_actions(self):
        self.actions = {}
        return self.actions


class DummyInterface():

    label_format = 'D{}'

    def __init__(self, ifc, idx=0, sd=None, tfrm=None, label='DummyInterface'):
        self.label = label
        self.render_color = (192, 192, 192)
        if tfrm is not None:
            self.tfrm = tfrm
        else:
            self.trfm = (np.identity(3), np.array([0., 0., 0.]))
        self.ifc = ifc
        self.idx = idx
        if sd is not None:
            self.sd = sd
        else:
            self.sd = ifc.od

    def __json_encode__(self):
        attrs = dict(vars(self))
        del attrs['parent']
        del attrs['tfrm']
        del attrs['ifc']
        del attrs['handles']
        del attrs['actions']
        return attrs

    def __str__(self):
        return str(self.ifc)

    def sync_to_restore(self, ele_model, surfs, gaps, tfrms):
        self.parent = ele_model
        self.tfrm = tfrms[self.idx]
        self.ifc = surfs[self.idx]

    def reference_interface(self):
        return self.ifc

    def sync_to_update(self, seq_model):
        self.idx = seq_model.ifcs.index(self.ifc)

    def update_size(self):
        self.sd = self.ifc.surface_od()
        return self.sd

    def render_shape(self):
        poly = self.ifc.full_profile((-self.sd, self.sd))
        return poly

    def render_handles(self, opt_model):
        self.handles = {}

        self.handles['shape'] = GraphicsHandle(self.render_shape(), self.tfrm,
                                               'polyline')

        return self.handles

    def handle_actions(self):
        self.actions = {}

        def get_adj_spaces():
            seq_model = self.parent.opt_model.seq_model
            if self.idx > 0:
                before = seq_model.gaps[self.idx-1].thi
            else:
                before = None
            if self.idx < seq_model.get_num_surfaces() - 1:
                after = seq_model.gaps[self.idx].thi
            else:
                after = None
            return (before, after)

        def set_adj_spaces(cur_value, change):
            seq_model = self.parent.opt_model.seq_model
            if cur_value[0] is not None:
                seq_model.gaps[self.idx-1].thi = cur_value[0] + change
            if cur_value[1] is not None:
                seq_model.gaps[self.idx].thi = cur_value[1] - change

        slide_action = {}
        slide_action['x'] = Action(get_adj_spaces, set_adj_spaces)
        self.actions['shape'] = slide_action

        return self.actions


class AirGap():

    label_format = 'AirGap {}'

    def __init__(self, g, ifc, idx=0, tfrm=None, label='AirGap'):
        if tfrm is not None:
            self.tfrm = tfrm
        else:
            self.trfm = (np.identity(3), np.array([0., 0., 0.]))
        self.label = label
        self.g = g
        self.ifc = ifc
        self.idx = idx

    def __json_encode__(self):
        attrs = dict(vars(self))
        del attrs['parent']
        del attrs['tfrm']
        del attrs['g']
        del attrs['ifc']
        del attrs['handles']
        del attrs['actions']
        return attrs

    def __str__(self):
        return str(self.g)

    def sync_to_restore(self, ele_model, surfs, gaps, tfrms):
        self.parent = ele_model
        self.g = gaps[self.idx]
        self.ifc = surfs[self.idx]
        self.tfrm = tfrms[self.idx]

    def reference_interface(self):
        return self.ifc

    def sync_to_update(self, seq_model):
        self.idx = seq_model.gaps.index(self.g)

    def update_size(self):
        pass

    def render_handles(self, opt_model):
        self.handles = {}

        poly_ct = []
        poly_ct.append([0., 0.])
        poly_ct.append([self.g.thi, 0.])
        self.handles['ct'] = GraphicsHandle(poly_ct, self.tfrm, 'polyline')

        return self.handles

    def handle_actions(self):
        self.actions = {}

        ct_action = {}
        ct_action['x'] = AttrAction(self.g, 'thi')
        self.actions['ct'] = ct_action

        return self.actions


class ElementModel:

    def __init__(self, opt_model):
        self.opt_model = opt_model
        self.elements = []

    def reset(self):
        self.__init__()

    def __json_encode__(self):
        attrs = dict(vars(self))
        del attrs['opt_model']
        return attrs

    def sync_to_restore(self, opt_model):
        self.opt_model = opt_model
        seq_model = opt_model.seq_model
        surfs = seq_model.ifcs
        gaps = seq_model.gaps
        tfrms = seq_model.compute_global_coords(1)

        # special processing for older models
        self.airgaps_from_sequence(seq_model, tfrms)
        self.add_dummy_interface_at_image(seq_model, tfrms)

        for i, e in enumerate(self.elements):
            e.sync_to_restore(self, surfs, gaps, tfrms)
            if not hasattr(e, 'label'):
                e.label = e.label_format.format(i+1)
        self.sequence_elements()
        self.relabel_airgaps()
#        self.list_elements()

    def elements_from_sequence(self, seq_model):
        """ generate an element list from a sequential model """

        # if there are elements in the list already, just return
        if len(self.elements) > 0:
            return

        num_elements = 0
        tfrms = seq_model.compute_global_coords(1)
        for i, g in enumerate(seq_model.gaps):
            s1 = seq_model.ifcs[i]
            tfrm = tfrms[i]
            if g.medium.name().lower() == 'air':
                if i > 0:
                    self.process_airgap(seq_model, i, g, s1, tfrm,
                                        num_elements, add_ele=True)
            else:  # a non-air medium
                # handle buried mirror, e.g. prism or Mangin mirror
                if s1.refract_mode is 'REFL':
                    gp = seq_model.gaps[i-1]
                    if gp.medium.name().lower() == g.medium.name().lower():
                        self.elements[-1].gaps.append(g)
                        continue

                s2 = seq_model.ifcs[i+1]
                sd = max(s1.surface_od(), s2.surface_od())
                e = Element(s1, s2, g, sd=sd, tfrm=tfrm, idx=i, idx2=i+1)
                num_elements += 1
                e.label = Element.label_format.format(num_elements)
                self.add_element(e)

        self.add_dummy_interface_at_image(seq_model, tfrms)

        self.relabel_airgaps()
#        self.list_elements()

    def process_airgap(self, seq_model, i, g, s, tfrm, num_ele, add_ele=True):
        if s.refract_mode is 'REFL' and add_ele:
            sd = s.surface_od()
            z_dir = seq_model.z_dir[i]
            m = Mirror(s, sd=sd, tfrm=tfrm, idx=i, z_dir=z_dir)
            num_ele += 1
            m.label = Mirror.label_format.format(num_ele)
            self.add_element(m)
        elif s.refract_mode is '':
            add_dummy = False
            if i == 0:
                add_dummy = True  # add dummy for the object
                dummy_label = 'Object'
            else:  # i > 0
                gp = seq_model.gaps[i-1]
                if gp.medium.name().lower() == 'air':
                    add_dummy = True
                    if seq_model.stop_surface == i:
                        dummy_label = 'Aperture Stop'
                    else:
                        dummy_label = DummyInterface.label_format.format(i)
            if add_dummy:
                tfrm = tfrm
                sd = s.surface_od()
                di = DummyInterface(s, sd=sd, tfrm=tfrm, idx=i)
                di.label = dummy_label
                self.add_element(di)
        elif isinstance(s, thinlens.ThinLens) and add_ele:
            te = ThinElement(s, tfrm=tfrm, idx=i)
            num_ele += 1
            te.label = ThinElement.label_format.format(num_ele)
            self.add_element(te)

        # add an AirGap
        ag = AirGap(g, s, idx=i, tfrm=tfrm)
        self.add_element(ag)

    def airgaps_from_sequence(self, seq_model, tfrms):
        """ add airgaps and dummy interfaces to an older version model """
        for e in self.elements:
            if isinstance(e, AirGap):
                return  # found an AirGap, model probably OK

        num_elements = 0
        seq_model = self.opt_model.seq_model
        for i, g in enumerate(seq_model.gaps):
            if g.medium.name().lower() == 'air':
                if i > 0:
                    s = seq_model.ifcs[i]
                    tfrm = tfrms[i]
                    self.process_airgap(seq_model, i, g, s, tfrm,
                                        num_elements, add_ele=False)

    def add_dummy_interface_at_image(self, seq_model, tfrms):
        if self.elements[-1].label == 'Image':
            return

        s = seq_model.ifcs[-1]
        idx = seq_model.get_num_surfaces() - 1
        di = DummyInterface(s, sd=s.surface_od(), tfrm=tfrms[-1], idx=idx)
        di.label = 'Image'
        self.add_element(di)

    def update_model(self):
        seq_model = self.opt_model.seq_model
        tfrms = seq_model.compute_global_coords(1)
        for e in self.elements:
            e.update_size()
            e.sync_to_update(seq_model)
            intrfc = e.reference_interface()
            try:
                i = seq_model.ifcs.index(intrfc)
            except ValueError:
                print("Interface {} not found".format(intrfc.lbl))
            else:
                e.tfrm = tfrms[i]

    def sequence_elements(self):
        """ Sort elements in order of reference interfaces in seq_model """
        seq_model = self.opt_model.seq_model
        self.elements.sort(key=lambda e:
                           seq_model.ifcs.index(e.reference_interface()))

    def relabel_airgaps(self):
        for i, e in enumerate(self.elements):
            if isinstance(e, AirGap):
                eb = self.elements[i-1].label
                ea = self.elements[i+1].label
                e.label = AirGap.label_format.format(eb + '-' + ea)

    def add_element(self, e):
        e.parent = self
        self.elements.append(e)

    def get_num_elements(self):
        return len(self.elements)

    def list_elements(self):
        for i, ele in enumerate(self.elements):
            print("%d: %s (%s): %s" %
                  (i, ele.label, type(ele).__name__, ele))