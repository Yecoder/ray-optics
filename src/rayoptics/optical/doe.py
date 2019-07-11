#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2019 Michael J. Hayford
""" Module diffractive/holographic optical elements

.. Created on Fri Jul  5 11:27:13 2019

.. codeauthor: Michael J. Hayford
"""


from math import sqrt
import numpy as np
from rayoptics.util.misc_math import normalize


def radial_phase_fct(pt, coefficients):
    """ evaluate the phase and slopes at **pt** """
    x, y, z = pt
    r_sqr = x*x + y*y
    dW = 0
    dWdX = 0
    dWdY = 0
    for i, c in enumerate(coefficients):
        dW += c*r_sqr**(i+1)
        r_exp = r_sqr**(i)
        dWdX += c*x*r_exp
        dWdY += c*y*r_exp
    return dW, dWdX, dWdY


class DiffractiveElement:
    def __init__(self, label='', coefficients=None, ref_wl=550., order=1,
                 phase_fct=None):
        self.label = label
        if coefficients is None:
            self.coefficients = []
        else:
            self.coefficients = coefficients
        self.ref_wl = ref_wl
        self.order = order
        self.phase_fct = phase_fct

    def __repr__(self):
        return (type(self).__name__ + '(label=' + repr(self.label) +
                ', coefficients=' + repr(self.coefficients) +
                ', ref_wl=' + repr(self.ref_wl) +
                ', order=' + repr(self.order) +
                ', phase_fct=' + repr(self.phase_fct) + ')')

    def list_doe(self):
        print("ref_pt: {:12.5f} {:12.5f} {:12.5f} {}"
              .format(self.ref_pt[0], self.ref_pt[1], self.ref_pt[2],
                      self.ref_virtual))

    def phase(self, pt, in_dir, srf_nrml, wl=None):
        normal = normalize(srf_nrml)
        in_cosI = np.dot(in_dir, normal)
        mu = 1.0 if wl is None else wl/self.ref_wl
        dW, dWdX, dWdY = self.phase_fct(pt, self.coefficients)
#        print(wl, mu, dW, dWdX, dWdY)
        b = in_cosI + mu*(normal[0]*dWdX + normal[1]*dWdY)
        c = mu*(mu*(dWdX**2 - dWdY**2)/2 + (in_dir[0]*dWdX - in_dir[1]*dWdY))
        Q = -b + sqrt(b*b - 2*c)
        out_dir = in_dir + mu*(np.array([dWdX, dWdY, 0])) + Q*normal
        return out_dir, dW


class HolographicElement:
    def __init__(self, lbl=''):
        self.label = lbl
        self.ref_pt = np.array([0., 0., -1e10])
        self.ref_virtual = False
        self.obj_pt = np.array([0., 0., -1e10])
        self.obj_virtual = False
        self.ref_wl = 550.0

    def list_hoe(self):
        print("ref_pt: {:12.5f} {:12.5f} {:12.5f} {}"
              .format(self.ref_pt[0], self.ref_pt[1], self.ref_pt[2],
                      self.ref_virtual))
        print("obj_pt: {:12.5f} {:12.5f} {:12.5f} {}"
              .format(self.obj_pt[0], self.obj_pt[1], self.obj_pt[2],
                      self.obj_virtual))

    def phase(self, pt, in_dir, srf_nrml, wl=None):
        normal = normalize(srf_nrml)
        ref_dir = normalize(pt - self.ref_pt)
        if self.ref_virtual:
            ref_dir = -ref_dir
        ref_cosI = np.dot(ref_dir, normal)
        obj_dir = normalize(pt - self.obj_pt)
        if self.obj_virtual:
            obj_dir = -obj_dir
        obj_cosI = np.dot(obj_dir, normal)
        in_cosI = np.dot(in_dir, normal)
        mu = 1.0 if wl is None else wl/self.ref_wl
        b = in_cosI + mu*(obj_cosI - ref_cosI)
        refp_cosI = np.dot(ref_dir, in_dir)
        objp_cosI = np.dot(obj_dir, in_dir)
        ro_cosI = np.dot(ref_dir, obj_dir)
        c = mu*(mu*(1.0 - ro_cosI) + (objp_cosI - refp_cosI))
        Q = -b + sqrt(b*b - 2*c)
        out_dir = in_dir + mu*(obj_dir - ref_dir) + Q*normal
        dW = 0.
        return out_dir, dW