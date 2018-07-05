# -*- coding: utf-8 -*-

# Copyright © 2018 Jean-Sébastien Gosselin
# https://github.com/jnsebgosselin/qwatson
#
# This file is part of PyGLD.
# Licensed under the terms of the GNU General Public License.

# ---- Standard imports

from collections.abc import Mapping

# ---- Third party imports

import numpy as np
from scipy.spatial import Delaunay

# ---- Local imports

from pygld.fluidproperties import HeatCarrierFluid
from pygld.heatpumps.utils import load_heatpump_database
from pygld.heatpumps.plots import plot_fitmodel_eval_from

corrtbl_afreeze = {}

tbl_fluid0 = {}
tbl_fluid0['name'] = 'water'
tbl_fluid0['fr'] = [0]
tbl_fluid0['CAPh'] = [1]
tbl_fluid0['CAPc'] = [1]
tbl_fluid0['COPh'] = [1]
tbl_fluid0['COPc'] = [1]
tbl_fluid0['Wh'] = [1]
tbl_fluid0['Wc'] = [1]
tbl_fluid0['WPD'] = [1]

tbl_fluid1 = {}
tbl_fluid1['name'] = 'prop_glycol'
tbl_fluid1['fr'] = [0, 0.05, 0.15, 0.25]
tbl_fluid1['CAPh'] = np.array([1, 0.989, 0.968, 0.947])
tbl_fluid1['CAPc'] = np.array([1, 0.995, 0.986, 0.978])
tbl_fluid1['Wh'] = np.array([1, 0.997, 0.990, 0.983])
tbl_fluid1['Wc'] = np.array([1, 1.003, 1.009, 1.014])
tbl_fluid1['COPh'] = tbl_fluid1['CAPh']/tbl_fluid1['Wh']
tbl_fluid1['COPc'] = tbl_fluid1['CAPc']/tbl_fluid1['Wc']
tbl_fluid1['WPD'] = [1, 1.070, 1.210, 1.360]

tbl_fluid2 = {}
tbl_fluid2['name'] = 'ethyl_glycol'
tbl_fluid2['fr'] = [0, 0.05, 0.15, 0.25]
tbl_fluid2['CAPh'] = np.array([1, 0.993, 0.980, 0.966])
tbl_fluid2['CAPc'] = np.array([1, 0.998, 0.994, 0.988])
tbl_fluid2['Wh'] = np.array([1, 0.998, 0.994, 0.990])
tbl_fluid2['Wc'] = np.array([1, 1.002, 1.004, 1.008])
tbl_fluid2['COPh'] = tbl_fluid1['CAPh']/tbl_fluid1['Wh']
tbl_fluid2['COPc'] = tbl_fluid1['CAPc']/tbl_fluid1['Wc']
tbl_fluid2['WPD'] = [1, 1.040, 1.120, 1.200]

corrtbl_afreeze[tbl_fluid0['name']] = tbl_fluid0
corrtbl_afreeze[tbl_fluid1['name']] = tbl_fluid1
corrtbl_afreeze[tbl_fluid2['name']] = tbl_fluid2


class HeatPump(object):

    def __init__(self):
        """
        TinHP  : temperature of the fluid entering the HP in ºC.
        model : model of the heat pump
        qbat  : building thermal load in kW (+ for cooling, - for heating)
                applied to the heatpump.
        fluid : heat carrier fluid type
        fr    : antifreeze volumetric fraction
        Vf    : fluid carrier volumetric flowrate in the heatpump in L/s
        """
        self._hpdb = load_heatpump_database()
        self.set_model(0)

        # Independent properties :

        self.TinHP = IndependentProp(cooling=28, heating=0)
        self.qbat = IndependentProp(cooling=16.5, heating=14.5)

        self.Vf = IndependentProp(
            cooling=0.05 * self.qbat.cooling, heating=0.05 * self.qbat.heating)
        self.fluid = 'water'
        self.fr = 0

        # Dependent properties :

        self._Tm = DependentProp()
        self._ToutHP = DependentProp()
        self._COP = DependentProp()
        self._CAP = DependentProp()
    def __str__(self):
        str_ = "model = %s\n\n" % self.model
        str_ += "qbat (%s): %0.2f kW\n" % ('heating', self.qbat.h)
        str_ += "qbat (%s): %0.2f kW\n" % ('cooling', self.qbat.c)
        str_ += 'Vf (%s): %0.2f L/s\n' % ('heating', self.Vf.h)
        str_ += 'Vf (%s): %0.2f L/s\n' % ('cooling', self.Vf.c)
        str_ += 'fluid  : %s\n' % self.fluid
        str_ += 'fr     : %s\n' % self.fr
        for mode in ['heating', 'cooling']:
            str_ += '\n'
            str_ += 'TinHP  (%s): %0.2f \u00B0C\n' % (mode, self.TinHP[mode])
            str_ += 'ToutHP (%s): %0.2f \u00B0C\n' % (mode, self.ToutHP[mode])
            str_ += 'Tm     (%s): %0.2f \u00B0C\n' % (mode, self.Tm[mode])
            str_ += 'COP    (%s): %0.2f\n' % (mode, self.COP[mode])
            str_ += 'CAP    (%s): %0.2f kW\n' % (mode, self.CAP[mode])
        return str_

    @property
    def hpdata(self):
        """Return the performance data table of the heat pump."""
        return self._hpdb[self.model]

    @property
    def model(self):
        """Return the name of the current heat pump."""
        return self._model

    def set_model(self, value):
        """
        Set the name of the heatpump either from an index or a key. If the
        index or key is not found in the database, an error is raised.
        """
        if isinstance(value, int):
            self._model = self.get_avail_heatpump_models()[value]
        elif isinstance(value, str):
            if value in list(self._hpdb.keys()):
                self._name = value
            else:
                raise ValueError("Heatpump '%s' not found in the database"
                                 % value)
        else:
            raise TypeError("'value' must be either an int or a str")

    # ---- Dependent properties

    @property
    def ToutHP(self):
        """
        Return the temperature of the water leaving the heat pump (LWT) in ºC.
        """
        self._ToutHP._heating_val = self.calcul_ToutHP('heating')
        self._ToutHP._cooling_val = self.calcul_ToutHP('cooling')
        return self._ToutHP

    @property
    def Tm(self):
        """Return the fluid mean temperature through the heat pump in ºC"""
        ToutHP, TinHP = self.ToutHP, self.TinHP
        self._Tm._heating_val = (TinHP.h + ToutHP.h)/2
        self._Tm._cooling_val = (TinHP.c + ToutHP.c)/2
        return self._Tm

    @property
    def COP(self):
        """Return the coefficient of performance of the heatpump."""
        self._COP._heating_val = self.interp('COPh', self.TinHP.h, self.Vf.h)
        self._COP._cooling_val = self.interp('COPc', self.TinHP.c, self.Vf.c)
        return self._COP

    @property
    def CAP(self):
        """Return the capacity of the heatpump in kW."""
        self._CAP._heating_val = self.interp('CAPh', self.TinHP.h, self.Vf.h)
        self._CAP._cooling_val = self.interp('CAPc', self.TinHP.c, self.Vf.c)
        return self._CAP

    # ---- Calculs

    def calcul_ToutHP_for_mode(self, mode):
        """
        Calcul the temperature of the fluid leaving the heat pump for the
        current mode of operation (cooling of heating).
        """

        # Calculate fluid properties :

        hcfluid = HeatCarrierFluid(self.fluid, self.TinHP[mode], self.fr)
        rhof = hcfluid.rho
        cpf = hcfluid.cp

        # Calculate ground load :

        COP = self.get_COP(mode)
        if mode == 'cooling':
            qgnd = self.qbat[mode] * (COP + 1) / COP
        elif mode == 'heating':
            qgnd = -self.qbat[mode] * (COP - 1) / COP

        # Calculate outflow fluid temperature :

        ToutHP = self.TinHP[mode] + qgnd/(self.Vf[mode]*rhof*cpf) * 10**6

        return ToutHP

    def interp(self, varname, ewt, gpm):
        """
        Evaluate the heatpump <varname> at the specifived ewt and gpm value
        with the equation-fit model.

        varname : COPc, COPh, CAPc, CAPh
        ewt : entering water temperature in the HP (ºC)
        gpm : volumetric flowrate in the HP (L/s)
        """

        A = self._hpdb[self.hpname]['models'][varname]

        y = (A[0] +
             A[1]*ewt + A[2]*ewt**2 +
             A[3]*gpm + A[4]*gpm**2 +
             A[5]*ewt*gpm)

        # Get the anti-freeze correction factor.

        afcorr = np.interp(self.fr,
                           corrtbl_afreeze[self.fluid]['fr'],
                           corrtbl_afreeze[self.fluid][varname])

        return y * afcorr

    # ---- Utility methods

    def in_table(self, varname, p1, p2):
        """
        Check whether the (p1, p2) point is inside or outside the data table
        for the specified variable. COP or CAP values evaluated outside the
        data table (extrapolation) must be used with care.

        Based on this stackoverflow answer:
        http://stackoverflow.com/a/16898636/4481445
        """
        y = self._hpdb[self.model][varname]
        indx = np.where(~np.isnan(y))[0]

        x1 = self._hpdb[self.model]['EWT'][indx]
        x2 = self._hpdb[self.model]['GPM'][indx]

        hull = Delaunay(np.vstack((x1, x2)).T)
        return bool(hull.find_simplex((p1, p2)) >= 0)

    def get_flowRange(self):
        """
        Return the minimum and maximum operational flowrate of the heatpump.
        """
        vmax = np.max(self._hpdb[self.model]['GPM'])
        vmin = np.min(self._hpdb[self.model]['GPM'])
        return vmin, vmax

    def plot_heatpump_model_goodness(self):
        """
        Produce a graph that shows the goodness of fit of the equation-fit
        models used to evaluate the COP and CAP values of the heatpump as a
        function of the entering water temperature (EWT) and volumetric
        flowrate.
        """
        plot_fitmodel_eval_from(self.hpdata)

    def get_avail_heatpump_models(self):
        """Return a list of all available heatpump models in the database."""
        return list(self._hpdb.keys())

    def print_avail_heatpump_models(self):
        """Print the list of the available heatpump models in the database."""
        models = self.get_avail_heatpump_models()
        N = len(models)
        max_indent = (N-1)//10
        for i, model in enumerate(models):
            indent = ' ' * (max_indent - i//100)
            print("%s%d - %s" % (indent, i, model))


class DependentProp(Mapping):
    """A dependent property of the heatpump."""

    COOLING_ATTRS = ['cooling', 'c']
    HEATING_ATTRS = ['heating', 'h']

    def __init__(self, parent, cooling=None, heating=None):
        super(DependentProp, self).__init__()
        self._parent = parent
        self._cooling = cooling
        self._heating = heating

    def __getitem__(self, key):
        """Returns the value saved in the store at key."""
        return self.__getattr__(key)

    def __getattr__(self, attr):
        if attr in self.COOLING_ATTRS:
            return self._cooling
        elif attr in self.HEATING_ATTRS:
            return self._heating
        else:
            return super().__getattr__(attr)

    def __setitem__(self, key, value):
        self.__setattr__(key, value)

    def __setattr__(self, attr, value):
        if attr in self.COOLING_ATTRS + self.HEATING_ATTRS:
            raise AttributeError('Cannot set attribute %s' % attr)
        else:
            super().__setattr__(attr, value)

    def __iter__(self):
        for x in [self._cooling, self._heating]:
            yield x

    def __len__(self, key):
        return 2

    def __str__(self):
        return "{'cooling': %f, 'heating': %f}" % (self.cooling, self.heating)


class IndependentProp(DependentProp):
    """An independent property of the heatpump."""

    def __setitem__(self, key, value):
        self.__setattr__(key, value)

    def __setattr__(self, attr, value):
        if attr in self.COOLING_ATTRS:
            self._cooling = value
            self._parent._varstate_has_changed()
        elif attr in self.HEATING_ATTRS:
            self._heating = value
            self._parent._varstate_has_changed()
        else:
            super().__setattr__(attr, value)


if __name__ == '__main__':
    heatpump = HeatPump()
    heatpump.plot_heatpump_model_goodness()
    hpdb = heatpump._hpdb
    print(heatpump.hpnames)
