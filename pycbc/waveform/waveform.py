# Copyright (C) 2012  Alex Nitz
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


#
# =============================================================================
#
#                                   Preamble
#
# =============================================================================
#
"""Convenience functions to genenerate gravitational wave templates and
waveforms.
"""

import os
import lal, numpy, copy
from pycbc.types import TimeSeries, FrequencySeries, zeros, Array
from pycbc.types import real_same_precision_as, complex_same_precision_as
import pycbc.scheme as _scheme
import inspect
from pycbc.fft import fft
from pycbc import pnutils, libutils
from pycbc.waveform import utils as wfutils
from pycbc.waveform import parameters
from pycbc.conversions import get_final_from_initial, tau_from_final_mass_spin
from pycbc.filter import interpolate_complex_frequency, resample_to_delta_t
import pycbc
from .spa_tmplt import spa_tmplt, spa_tmplt_norm, spa_tmplt_end, \
                      spa_tmplt_precondition, spa_amplitude_factor, \
                      spa_length_in_time

class NoWaveformError(Exception):
    """This should be raised if generating a waveform would just result in all
    zeros being returned, e.g., if a requested `f_final` is <= `f_lower`.
    """
    pass


class FailedWaveformError(Exception):
    """This should be raised if a waveform fails to generate.
    """
    pass

# If this is set to True, waveform generation codes will try to regenerate
# waveforms with known failure conditions to try to avoid the failure. For
# example SEOBNRv3 waveforms would be regenerated with double the sample rate.
# If this is set to False waveform failures will always raise exceptions
fail_tolerant_waveform_generation = True

default_args = \
    (parameters.fd_waveform_params.default_dict() +
     parameters.td_waveform_params).default_dict()

default_sgburst_args = {'eccentricity':0, 'polarization':0}
sgburst_required_args = ['q','frequency','hrss']

# td, fd, filter waveforms generated on the CPU
_lalsim_td_approximants = {}
_lalsim_fd_approximants = {}
_lalsim_enum = {}
_lalsim_sgburst_approximants = {}

def _check_lal_pars(p):
    """ Create a laldict object from the dictionary of waveform parameters

    Parameters
    ----------
    p: dictionary
        The dictionary of lalsimulation paramaters

    Returns
    -------
    laldict: LalDict
        The lal type dictionary to pass to the lalsimulation waveform functions.
    """
    lal_pars = lal.CreateDict()
    #nonGRparams can be straightforwardly added if needed, however they have to
    # be invoked one by one
    if p['phase_order']!=-1:
        lalsimulation.SimInspiralWaveformParamsInsertPNPhaseOrder(lal_pars,int(p['phase_order']))
    if p['amplitude_order']!=-1:
        lalsimulation.SimInspiralWaveformParamsInsertPNAmplitudeOrder(lal_pars,int(p['amplitude_order']))
    if p['spin_order']!=-1:
        lalsimulation.SimInspiralWaveformParamsInsertPNSpinOrder(lal_pars,int(p['spin_order']))
    if p['tidal_order']!=-1:
        lalsimulation.SimInspiralWaveformParamsInsertPNTidalOrder(lal_pars, p['tidal_order'])
    if p['eccentricity_order']!=-1:
        lalsimulation.SimInspiralWaveformParamsInsertPNEccentricityOrder(lal_pars, p['eccentricity_order'])
    if p['lambda1'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertTidalLambda1(lal_pars, p['lambda1'])
    if p['lambda2'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertTidalLambda2(lal_pars, p['lambda2'])
    if p['lambda_octu1'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertTidalOctupolarLambda1(lal_pars, p['lambda_octu1'])
    if p['lambda_octu2'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertTidalOctupolarLambda2(lal_pars, p['lambda_octu2'])
    if p['quadfmode1'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertTidalQuadrupolarFMode1(lal_pars, p['quadfmode1'])
    if p['quadfmode2'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertTidalQuadrupolarFMode2(lal_pars, p['quadfmode2'])
    if p['octufmode1'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertTidalOctupolarFMode1(lal_pars, p['octufmode1'])
    if p['octufmode2'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertTidalOctupolarFMode2(lal_pars, p['octufmode2'])
    if p['dquad_mon1'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertdQuadMon1(lal_pars, p['dquad_mon1'])
    if p['dquad_mon2'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertdQuadMon2(lal_pars, p['dquad_mon2'])
    if p['numrel_data']:
        lalsimulation.SimInspiralWaveformParamsInsertNumRelData(lal_pars, str(p['numrel_data']))
    if p['modes_choice']:
        lalsimulation.SimInspiralWaveformParamsInsertModesChoice(lal_pars, p['modes_choice'])
    if p['frame_axis']:
        lalsimulation.SimInspiralWaveformParamsInsertFrameAxis(lal_pars, p['frame_axis'])
    if p['side_bands']:
        lalsimulation.SimInspiralWaveformParamsInsertSideband(lal_pars, p['side_bands'])
    if p['mode_array'] is not None:
        ma = lalsimulation.SimInspiralCreateModeArray()
        for l,m in p['mode_array']:
            lalsimulation.SimInspiralModeArrayActivateMode(ma, l, m)
        lalsimulation.SimInspiralWaveformParamsInsertModeArray(lal_pars, ma)
    #TestingGR parameters:
    if p['dchi0'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDChi0(lal_pars,p['dchi0'])
    if p['dchi1'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDChi1(lal_pars,p['dchi1'])
    if p['dchi2'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDChi2(lal_pars,p['dchi2'])
    if p['dchi3'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDChi3(lal_pars,p['dchi3'])
    if p['dchi4'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDChi4(lal_pars,p['dchi4'])
    if p['dchi5'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDChi5(lal_pars,p['dchi5'])
    if p['dchi5l'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDChi5L(lal_pars,p['dchi5l'])
    if p['dchi6'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDChi6(lal_pars,p['dchi6'])
    if p['dchi6l'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDChi6L(lal_pars,p['dchi6l'])
    if p['dchi7'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDChi7(lal_pars,p['dchi7'])
    if p['dalpha1'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDAlpha1(lal_pars,p['dalpha1'])
    if p['dalpha2'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDAlpha2(lal_pars,p['dalpha2'])
    if p['dalpha3'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDAlpha3(lal_pars,p['dalpha3'])
    if p['dalpha4'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDAlpha4(lal_pars,p['dalpha4'])
    if p['dalpha5'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDAlpha5(lal_pars,p['dalpha5'])
    if p['dbeta1'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDBeta1(lal_pars,p['dbeta1'])
    if p['dbeta2'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDBeta2(lal_pars,p['dbeta2'])
    if p['dbeta3'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertNonGRDBeta3(lal_pars,p['dbeta3'])
    if p['PrecThresholdMband'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertPhenomXPHMThresholdMband(
            lal_pars,
            p['PrecThresholdMband'],
        )
    if p['ThresholdMband'] is not None:
        lalsimulation.SimInspiralWaveformParamsInsertPhenomXHMThresholdMband(
            lal_pars,
            p['ThresholdMband'],
        )
    return lal_pars

def _lalsim_td_waveform(**p):
    lal_pars = _check_lal_pars(p)
    #nonGRparams can be straightforwardly added if needed, however they have to
    # be invoked one by one
    try:
        hp1, hc1 = lalsimulation.SimInspiralChooseTDWaveform(
               float(pnutils.solar_mass_to_kg(p['mass1'])),
               float(pnutils.solar_mass_to_kg(p['mass2'])),
               float(p['spin1x']), float(p['spin1y']), float(p['spin1z']),
               float(p['spin2x']), float(p['spin2y']), float(p['spin2z']),
               pnutils.megaparsecs_to_meters(float(p['distance'])),
               float(p['inclination']), float(p['coa_phase']),
               float(p['long_asc_nodes']), float(p['eccentricity']), float(p['mean_per_ano']),
               float(p['delta_t']), float(p['f_lower']), float(p['f_ref']),
               lal_pars,
               _lalsim_enum[p['approximant']])
    except RuntimeError:
        if not fail_tolerant_waveform_generation:
            raise
        # For some cases failure modes can occur. Here we add waveform-specific
        # instructions to try to work with waveforms that are known to fail.
        if 'SEOBNRv3' in p['approximant']:
            # Try doubling the sample time and redoing.
            # Don't want to get stuck in a loop though!
            if 'delta_t_orig' not in p:
                p['delta_t_orig'] = p['delta_t']
            p['delta_t'] = p['delta_t'] / 2.
            if p['delta_t_orig'] / p['delta_t'] > 9:
                raise
            hp, hc = _lalsim_td_waveform(**p)
            p['delta_t'] = p['delta_t_orig']
            hp = resample_to_delta_t(hp, hp.delta_t*2)
            hc = resample_to_delta_t(hc, hc.delta_t*2)
            return hp, hc
        raise

    #lal.DestroyDict(lal_pars)

    hp = TimeSeries(hp1.data.data[:], delta_t=hp1.deltaT, epoch=hp1.epoch)
    hc = TimeSeries(hc1.data.data[:], delta_t=hc1.deltaT, epoch=hc1.epoch)

    return hp, hc

_lalsim_td_waveform.required = parameters.cbc_td_required

def _spintaylor_aligned_prec_swapper(**p):
    """
    SpinTaylorF2 is only single spin, it also struggles with anti-aligned spin
    waveforms. This construct chooses between the aligned-twospin TaylorF2 model
    and the precessing singlespin SpinTaylorF2 models. If aligned spins are
    given, use TaylorF2, if nonaligned spins are given use SpinTaylorF2. In
    the case of nonaligned doublespin systems the code will fail at the
    waveform generator level.
    """
    orig_approximant = p['approximant']
    if p['spin2x'] == 0 and p['spin2y'] == 0 and p['spin1x'] == 0 and \
                                                              p['spin1y'] == 0:
        p['approximant'] = 'TaylorF2'
    else:
        p['approximant'] = 'SpinTaylorF2'
    hp, hc = _lalsim_fd_waveform(**p)
    p['approximant'] = orig_approximant
    return hp, hc

def _lalsim_fd_waveform(**p):
    lal_pars = _check_lal_pars(p)
    hp1, hc1 = lalsimulation.SimInspiralChooseFDWaveform(
               float(pnutils.solar_mass_to_kg(p['mass1'])),
               float(pnutils.solar_mass_to_kg(p['mass2'])),
               float(p['spin1x']), float(p['spin1y']), float(p['spin1z']),
               float(p['spin2x']), float(p['spin2y']), float(p['spin2z']),
               pnutils.megaparsecs_to_meters(float(p['distance'])),
               float(p['inclination']), float(p['coa_phase']),
               float(p['long_asc_nodes']), float(p['eccentricity']), float(p['mean_per_ano']),
               p['delta_f'], float(p['f_lower']), float(p['f_final']), float(p['f_ref']),
               lal_pars,
               _lalsim_enum[p['approximant']])

    hp = FrequencySeries(hp1.data.data[:], delta_f=hp1.deltaF,
                            epoch=hp1.epoch)

    hc = FrequencySeries(hc1.data.data[:], delta_f=hc1.deltaF,
                            epoch=hc1.epoch)
    #lal.DestroyDict(lal_pars)
    return hp, hc

_lalsim_fd_waveform.required = parameters.cbc_fd_required

def _lalsim_sgburst_waveform(**p):
    hp, hc = lalsimulation.SimBurstSineGaussian(float(p['q']),
               float(p['frequency']),
               float(p['hrss']),
               float(p['eccentricity']),
               float(p['polarization']),
               float(p['delta_t']))

    hp = TimeSeries(hp.data.data[:], delta_t=hp.deltaT, epoch=hp.epoch)
    hc = TimeSeries(hc.data.data[:], delta_t=hc.deltaT, epoch=hc.epoch)

    return hp, hc

# Populate waveform approximants from lalsimulation if the library is
# available
try:
    import lalsimulation
    for approx_enum in range(0, lalsimulation.NumApproximants):
        if lalsimulation.SimInspiralImplementedTDApproximants(approx_enum):
            approx_name = lalsimulation.GetStringFromApproximant(approx_enum)
            _lalsim_enum[approx_name] = approx_enum
            _lalsim_td_approximants[approx_name] = _lalsim_td_waveform

    for approx_enum in range(0, lalsimulation.NumApproximants):
        if lalsimulation.SimInspiralImplementedFDApproximants(approx_enum):
            approx_name = lalsimulation.GetStringFromApproximant(approx_enum)
            _lalsim_enum[approx_name] = approx_enum
            _lalsim_fd_approximants[approx_name] = _lalsim_fd_waveform

    # sine-Gaussian burst
    for approx_enum in range(0, lalsimulation.NumApproximants):
        if lalsimulation.SimInspiralImplementedFDApproximants(approx_enum):
            approx_name = lalsimulation.GetStringFromApproximant(approx_enum)
            _lalsim_enum[approx_name] = approx_enum
            _lalsim_sgburst_approximants[approx_name] = _lalsim_sgburst_waveform
except ImportError:
    lalsimulation = libutils.import_optional('lalsimulation')

cpu_sgburst = _lalsim_sgburst_approximants
cpu_td = dict(_lalsim_td_approximants.items())
cpu_fd = _lalsim_fd_approximants

# Waveforms written in CUDA
_cuda_td_approximants = {}
_cuda_fd_approximants = {}

if pycbc.HAVE_CUDA:
    from pycbc.waveform.pycbc_phenomC_tmplt import imrphenomc_tmplt
    from pycbc.waveform.SpinTaylorF2 import spintaylorf2 as cuda_spintaylorf2
    _cuda_fd_approximants["IMRPhenomC"] = imrphenomc_tmplt
    _cuda_fd_approximants["SpinTaylorF2"] = cuda_spintaylorf2

cuda_td = dict(list(_lalsim_td_approximants.items()) + list(_cuda_td_approximants.items()))
cuda_fd = dict(list(_lalsim_fd_approximants.items()) + list(_cuda_fd_approximants.items()))

# List the various available approximants ####################################

def print_td_approximants():
    print("LalSimulation Approximants")
    for approx in _lalsim_td_approximants.keys():
        print("  " + approx)
    print("CUDA Approximants")
    for approx in _cuda_td_approximants.keys():
        print("  " + approx)

def print_fd_approximants():
    print("LalSimulation Approximants")
    for approx in _lalsim_fd_approximants.keys():
        print("  " + approx)
    print("CUDA Approximants")
    for approx in _cuda_fd_approximants.keys():
        print("  " + approx)

def print_sgburst_approximants():
    print("LalSimulation Approximants")
    for approx in _lalsim_sgburst_approximants.keys():
        print("  " + approx)

def td_approximants(scheme=_scheme.mgr.state):
    """Return a list containing the available time domain approximants for
       the given processing scheme.
    """
    return list(td_wav[type(scheme)].keys())

def fd_approximants(scheme=_scheme.mgr.state):
    """Return a list containing the available fourier domain approximants for
       the given processing scheme.
    """
    return list(fd_wav[type(scheme)].keys())

def sgburst_approximants(scheme=_scheme.mgr.state):
    """Return a list containing the available time domain sgbursts for
       the given processing scheme.
    """
    return list(sgburst_wav[type(scheme)].keys())

def filter_approximants(scheme=_scheme.mgr.state):
    """Return a list of fourier domain approximants including those
       written specifically as templates.
    """
    return list(filter_wav[type(scheme)].keys())

# Input parameter handling ###################################################

def get_obj_attrs(obj):
    """ Return a dictionary built from the attributes of the given object.
    """
    pr = {}
    if obj is not None:
        if isinstance(obj, numpy.core.records.record):
            for name in obj.dtype.names:
                pr[name] = getattr(obj, name)
        elif hasattr(obj, '__dict__') and obj.__dict__:
            pr = obj.__dict__
        elif hasattr(obj, '__slots__'):
            for slot in obj.__slots__:
                if hasattr(obj, slot):
                    pr[slot] = getattr(obj, slot)
        elif isinstance(obj, dict):
            pr = obj.copy()
        else:
            for name in dir(obj):
                try:
                    value = getattr(obj, name)
                    if not name.startswith('__') and not inspect.ismethod(value):
                        pr[name] = value
                except:
                    continue

    return pr


def parse_mode_array(input_params):
    """Ensures mode_array argument in a dictionary of input parameters is
    a list of tuples of (l, m), where l and m are ints.

    Accepted formats for the ``mode_array`` argument is a list of tuples of
    ints (e.g., ``[(2, 2), (3, 3), (4, 4)]``), a space-separated string giving
    the modes (e.g., ``22 33 44``), or an array of ints or floats (e.g.,
    ``[22., 33., 44.]``.
    """
    if 'mode_array' in input_params and input_params['mode_array'] is not None:
        mode_array = input_params['mode_array']
        if isinstance(mode_array, str):
            mode_array = mode_array.split()
        if not isinstance(mode_array, (numpy.ndarray, list)):
            mode_array = [mode_array]
        for ii, ma in enumerate(mode_array):
            # if ma is a float or int, convert to str (e.g., 22. -> '22'), so
            # that...
            if isinstance(ma, (float, int)):
                ma = str(int(ma))
            # if ma is a str convert to (int, int) (e.g., '22' -> (2, 2))
            if isinstance(ma, str):
                l, m = ma
                ma = (int(l), int(m))
            mode_array[ii] = ma
        input_params['mode_array'] = mode_array
    return input_params


def props(obj, **kwargs):
    """ Return a dictionary built from the combination of defaults, kwargs,
    and the attributes of the given object.
    """
    pr = get_obj_attrs(obj)
    pr.update(kwargs)
    # Get the parameters to generate the waveform
    # Note that keyword arguments override values in the template object
    input_params = default_args.copy()
    input_params.update(pr)
    # if mode array present and is a string, convert to a list of tuples
    input_params = parse_mode_array(input_params)
    return input_params

def check_args(args, required_args):
    """ check that required args are given """
    missing = []
    for arg in required_args:
        if (arg not in args) or (args[arg] is None):
            missing.append(arg)

    if len(missing) != 0:
        raise ValueError("Please provide {}".format(', '.join(missing)))

# Input parameter handling for bursts ########################################

def props_sgburst(obj, **kwargs):
    pr = {}
    if obj is not None:
        for name in dir(obj):
            try:
                value = getattr(obj, name)
                if not name.startswith('__') and not inspect.ismethod(value):
                    pr[name] = value
            except:
                continue

    # Get the parameters to generate the waveform
    # Note that keyword arguments override values in the template object
    input_params = default_sgburst_args.copy()
    input_params.update(pr)
    input_params.update(kwargs)

    return input_params

# Waveform generation ########################################################
fd_sequence = {}
fd_det_sequence = {}
fd_det = {}

def _lalsim_fd_sequence(**p):
    """ Shim to interface to lalsimulation SimInspiralChooseFDWaveformSequence
    """
    lal_pars = _check_lal_pars(p)
    hp, hc = lalsimulation.SimInspiralChooseFDWaveformSequence(
               float(p['coa_phase']),
               float(pnutils.solar_mass_to_kg(p['mass1'])),
               float(pnutils.solar_mass_to_kg(p['mass2'])),
               float(p['spin1x']), float(p['spin1y']), float(p['spin1z']),
               float(p['spin2x']), float(p['spin2y']), float(p['spin2z']),
               float(p['f_ref']),
               pnutils.megaparsecs_to_meters(float(p['distance'])),
               float(p['inclination']),
               lal_pars,
               _lalsim_enum[p['approximant']],
               p['sample_points'].lal())
    return Array(hp.data.data), Array(hc.data.data)
_lalsim_fd_sequence.required = parameters.cbc_fd_required

for apx in _lalsim_enum:
    fd_sequence[apx] = _lalsim_fd_sequence


def get_fd_waveform_sequence(template=None, **kwds):
    """Return values of the waveform evaluated at the sequence of frequency
    points. The waveform generator doesn't include detector response.

    Parameters
    ----------
    template: object
        An object that has attached properties. This can be used to substitute
        for keyword arguments. A common example would be a row in an xml table.
    {params}

    Returns
    -------
    hplustilde: Array
        The plus phase of the waveform in frequency domain evaluated at the
    frequency points.
    hcrosstilde: Array
        The cross phase of the waveform in frequency domain evaluated at the
    frequency points.
    """
    input_params = props(template, **kwds)
    input_params['delta_f'] = -1
    input_params['f_lower'] = -1
    if input_params['approximant'] not in fd_sequence:
        raise ValueError("Approximant %s not available" %
                            (input_params['approximant']))
    wav_gen = fd_sequence[input_params['approximant']]
    if hasattr(wav_gen, 'required'):
        required = wav_gen.required
    else:
        required = parameters.fd_required
    check_args(input_params, required)
    return wav_gen(**input_params)

def get_fd_det_waveform_sequence(template=None, **kwds):
    """Return values of the waveform evaluated at the sequence of frequency
    points. The waveform generator includes detector response.

    Parameters
    ----------
    template: object
        An object that has attached properties. This can be used to substitute
        for keyword arguments. A common example would be a row in an xml table.
    {params}

    Returns
    -------
    dict
        The detector-frame waveform (with detector response) in frequency
        domain evaluated at the frequency points. Keys are requested data
        channels, values are FrequencySeries.
    """
    input_params = props(template, **kwds)
    input_params['delta_f'] = -1
    input_params['f_lower'] = -1
    if input_params['approximant'] not in fd_det_sequence:
        raise ValueError("Approximant %s not available" %
                            (input_params['approximant']))
    wav_gen = fd_det_sequence[input_params['approximant']]
    if hasattr(wav_gen, 'required'):
        required = wav_gen.required
    else:
        required = parameters.fd_required
    check_args(input_params, required)
    return wav_gen(**input_params)

get_fd_waveform_sequence.__doc__ = get_fd_waveform_sequence.__doc__.format(
    params=parameters.fd_waveform_sequence_params.docstr(prefix="    ",
           include_label=False).lstrip(' '))
get_fd_det_waveform_sequence.__doc__ = get_fd_det_waveform_sequence.__doc__.format(
    params=parameters.fd_waveform_sequence_params.docstr(prefix="    ",
           include_label=False).lstrip(' '))

def get_td_waveform(template=None, **kwargs):
    """Return the plus and cross polarizations of a time domain waveform.

    Parameters
    ----------
    template: object
        An object that has attached properties. This can be used to subsitute
        for keyword arguments. A common example would be a row in an xml table.
    {params}

    Returns
    -------
    hplus: TimeSeries
        The plus polarization of the waveform.
    hcross: TimeSeries
        The cross polarization of the waveform.
    """
    input_params = props(template, **kwargs)
    wav_gen = td_wav[type(_scheme.mgr.state)]
    if input_params['approximant'] not in wav_gen:
        raise ValueError("Approximant %s not available" %
                            (input_params['approximant']))
    wav_gen = wav_gen[input_params['approximant']]
    if hasattr(wav_gen, 'required'):
        required = wav_gen.required
    else:
        required = parameters.td_required
    check_args(input_params, required)
    return wav_gen(**input_params)

get_td_waveform.__doc__ = get_td_waveform.__doc__.format(
    params=parameters.td_waveform_params.docstr(prefix="    ",
           include_label=False).lstrip(' '))

def get_fd_waveform(template=None, **kwargs):
    """Return a frequency domain gravitational waveform.

    Parameters
    ----------
    template: object
        An object that has attached properties. This can be used to substitute
        for keyword arguments. A common example would be a row in an xml table.
    {params}

    Returns
    -------
    hplustilde: FrequencySeries
        The plus phase of the waveform in frequency domain.
    hcrosstilde: FrequencySeries
        The cross phase of the waveform in frequency domain.
    """
    input_params = props(template, **kwargs)
    wav_gen = fd_wav[type(_scheme.mgr.state)]
    if input_params['approximant'] not in wav_gen:
        raise ValueError("Approximant %s not available" %
                            (input_params['approximant']))
    try:
        ffunc = input_params.pop('f_final_func')
        if ffunc != '':
            # convert the frequency function to a value
            input_params['f_final'] = pnutils.named_frequency_cutoffs[ffunc](
                input_params)
            # if the f_final is < f_lower, raise a NoWaveformError
            if 'f_final' in input_params and \
                    (input_params['f_lower']+input_params['delta_f'] >=
                     input_params['f_final']):
                raise NoWaveformError("cannot generate waveform: f_lower >= "
                                      "f_final")
    except KeyError:
        pass
    wav_gen = wav_gen[input_params['approximant']]
    if hasattr(wav_gen, 'required'):
        required = wav_gen.required
    else:
        required = parameters.fd_required
    check_args(input_params, required)
    return wav_gen(**input_params)


get_fd_waveform.__doc__ = get_fd_waveform.__doc__.format(
    params=parameters.fd_waveform_params.docstr(prefix="    ",
           include_label=False).lstrip(' '))

def get_fd_waveform_from_td(**params):
    """ Return time domain version of fourier domain approximant.

    This returns a frequency domain version of a fourier domain approximant,
    with padding and tapering at the start of the waveform.

    Parameters
    ----------
    params: dict
        The parameters defining the waveform to generator.
        See `get_td_waveform`.

    Returns
    -------
    hp: pycbc.types.FrequencySeries
        Plus polarization time series
    hc: pycbc.types.FrequencySeries
        Cross polarization time series
    """

    # determine the duration to use
    full_duration = duration = get_waveform_filter_length_in_time(**params)
    nparams = params.copy()

    while full_duration < duration * 1.5:
        full_duration = get_waveform_filter_length_in_time(**nparams)
        nparams['f_lower'] -= 1

    if 'f_fref' not in nparams:
        nparams['f_ref'] = params['f_lower']

    # We'll try to do the right thing and figure out what the frequency
    # end is. Otherwise, we'll just assume 2048 Hz.
    # (consider removing as we hopefully have better estimates for more
    # approximants
    try:
        f_end = get_waveform_end_frequency(**params)
        delta_t = (0.5 / pnutils.nearest_larger_binary_number(f_end))
    except:
        delta_t = 1.0 / 2048

    nparams['delta_t'] = delta_t
    hp, hc = get_td_waveform(**nparams)

    # Resize to the right duration
    tsamples = int(1.0 / params['delta_f'] / delta_t)

    if tsamples < len(hp):
        raise ValueError("The frequency spacing (df = {}) is too low to "
                         "generate the {} approximant from the time "
                         "domain".format(params['delta_f'], params['approximant']))

    hp.resize(tsamples)
    hc.resize(tsamples)

    # apply the tapering, we will use a safety factor here to allow for
    # somewhat innacurate duration difference estimation.
    window = (full_duration - duration) * 0.8
    hp = wfutils.td_taper(hp, hp.start_time, hp.start_time + window)
    hc = wfutils.td_taper(hc, hc.start_time, hc.start_time + window)

    # avoid wraparound
    hp = hp.to_frequencyseries().cyclic_time_shift(hp.start_time)
    hc = hc.to_frequencyseries().cyclic_time_shift(hc.start_time)
    return hp, hc

def get_fd_det_waveform(template=None, **kwargs):
    """Return a frequency domain gravitational waveform.
    The waveform generator includes detector response.

    Parameters
    ----------
    template: object
        An object that has attached properties. This can be used to substitute
        for keyword arguments. An example would be a row in an xml table.
    {params}

    Returns
    -------
    dict
        The detector-frame waveform (with detector response) in frequency
        domain. Keys are requested data channels, values are FrequencySeries.
    """
    input_params = props(template, **kwargs)
    if 'f_lower' not in input_params:
        input_params['f_lower'] = -1
    if input_params['approximant'] not in fd_det:
        raise ValueError("Approximant %s not available" %
                            (input_params['approximant']))
    wav_gen = fd_det[input_params['approximant']]
    if hasattr(wav_gen, 'required'):
        required = wav_gen.required
    else:
        required = parameters.fd_required
    check_args(input_params, required)
    return wav_gen(**input_params)

get_fd_det_waveform.__doc__ = get_fd_det_waveform.__doc__.format(
    params=parameters.fd_waveform_params.docstr(prefix="    ",
           include_label=False).lstrip(' '))

def _base_get_td_waveform_from_fd(template=None, rwrap=None, **params):
    """ The base function to calculate time domain version of fourier
    domain approximant which not include or includes detector response.
    Called by `get_td_waveform_from_fd` and `get_td_det_waveform_from_fd_det`.
    """
    kwds = props(template, **params)
    nparams = kwds.copy()

    if rwrap is None:
        # In the `pycbc.waveform.parameters` module, spin1z and
        # spin2z have the default value 0. Users must have input
        # masses, so no else is needed.
        mass_spin_params = set(['mass1', 'mass2', 'spin1z', 'spin2z'])
        if mass_spin_params.issubset(set(nparams.keys())):
            m_final, spin_final = get_final_from_initial(
                mass1=nparams['mass1'], mass2=nparams['mass2'],
                spin1z=nparams['spin1z'], spin2z=nparams['spin2z'])
            rwrap = tau_from_final_mass_spin(m_final, spin_final) * 10
            if rwrap < 5:
                # Long enough for very massive BBHs in XG detectors,
                # up to (3000, 3000) solar mass, while still not a
                # computational burden for 2G cases.
                rwrap = 5

    if nparams['approximant'] not in _filter_time_lengths:
        raise ValueError("Approximant %s _filter_time_lengths function \
                         not available" % (nparams['approximant']))
    # determine the duration to use
    full_duration = duration = get_waveform_filter_length_in_time(**nparams)

    while full_duration < duration * 1.5:
        full_duration = get_waveform_filter_length_in_time(**nparams)
        nparams['f_lower'] *= 0.99
        if 't_obs_start' in nparams and \
           full_duration >= nparams['t_obs_start']:
            break

    if 'f_ref' not in nparams:
        nparams['f_ref'] = params['f_lower']

    # factor to ensure the vectors are all large enough. We don't need to
    # completely trust our duration estimator in this case, at a small
    # increase in computational cost
    fudge_duration = (max(0, full_duration) + .1 + rwrap) * 1.5
    fsamples = int(fudge_duration / nparams['delta_t'])
    N = pnutils.nearest_larger_binary_number(fsamples)
    fudge_duration = N * nparams['delta_t']

    nparams['delta_f'] = 1.0 / fudge_duration
    tsize = int(1.0 / nparams['delta_t'] /  nparams['delta_f'])
    fsize = tsize // 2 + 1

    if nparams['approximant'] not in fd_det:
        hp, hc = get_fd_waveform(**nparams)
        # Resize to the right sample rate
        hp.resize(fsize)
        hc.resize(fsize)

        # avoid wraparound
        hp = hp.cyclic_time_shift(-rwrap)
        hc = hc.cyclic_time_shift(-rwrap)

        hp = wfutils.fd_to_td(hp, delta_t=params['delta_t'],
                              left_window=(nparams['f_lower'],
                                           params['f_lower']))
        hc = wfutils.fd_to_td(hc, delta_t=params['delta_t'],
                              left_window=(nparams['f_lower'],
                                           params['f_lower']))
        return hp, hc
    else:
        wfs = get_fd_det_waveform(**nparams)
        for ifo in wfs.keys():
            wfs[ifo].resize(fsize)
            # avoid wraparound
            wfs[ifo] = wfs[ifo].cyclic_time_shift(-rwrap)
            wfs[ifo] = wfutils.fd_to_td(wfs[ifo], delta_t=kwds['delta_t'],
                                        left_window=(nparams['f_lower'],
                                        kwds['f_lower']))
        return wfs

def get_td_waveform_from_fd(rwrap=None, **params):
    """ Return time domain version of fourier domain approximant.

    This returns a time domain version of a fourier domain approximant, with
    padding and tapering at the start of the waveform.

    Parameters
    ----------
    rwrap: float
        Cyclic time shift parameter in seconds. A fudge factor to ensure
        that the entire time series is contiguous in the array and not
        wrapped around the end.
    params: dict
        The parameters defining the waveform to generator.
        See `get_fd_waveform`.

    Returns
    -------
    hp: pycbc.types.TimeSeries
        Plus polarization time series
    hc: pycbc.types.TimeSeries
        Cross polarization time series
    """
    return _base_get_td_waveform_from_fd(None, rwrap, **params)

def get_td_det_waveform_from_fd_det(template=None, rwrap=None, **params):
    """ Return time domain version of fourier domain approximant which
    includes detector response, with padding and tapering at the start
    of the waveform.

    Parameters
    ----------
    rwrap: float
        Cyclic time shift parameter in seconds. A fudge factor to ensure
        that the entire time series is contiguous in the array and not
        wrapped around the end.
    params: dict
        The parameters defining the waveform to generator.
        See `get_fd_det_waveform`.

    Returns
    -------
    dict
        The detector-frame waveform (with detector response) in time
        domain. Keys are requested data channels.
    """
    return _base_get_td_waveform_from_fd(template, rwrap, **params)

get_td_det_waveform_from_fd_det.__doc__ = \
    get_td_det_waveform_from_fd_det.__doc__.format(
        params=parameters.td_waveform_params.docstr(prefix="    ",
            include_label=False).lstrip(' '))

def get_interpolated_fd_waveform(dtype=numpy.complex64, return_hc=True,
                                 **params):
    """ Return a fourier domain waveform approximant, using interpolation
    """

    def rulog2(val):
        return 2.0 ** numpy.ceil(numpy.log2(float(val)))

    orig_approx = params['approximant']
    params['approximant'] = params['approximant'].replace('_INTERP', '')
    df = params['delta_f']

    if 'duration' not in params:
        duration = get_waveform_filter_length_in_time(**params)
    elif params['duration'] > 0:
        duration = params['duration']
    else:
        err_msg = "Waveform duration must be greater than 0."
        raise ValueError(err_msg)

    #FIXME We should try to get this length directly somehow
    # I think this number should be conservative
    ringdown_padding = 0.5

    df_min = 1.0 / rulog2(duration + ringdown_padding)
    # FIXME: I don't understand this, but waveforms with df_min < 0.5 will chop
    #        off the inspiral when using ringdown_padding - 0.5.
    #        Also, if ringdown_padding is set to a very small
    #        value we can see cases where the ringdown is chopped.
    if df_min > 0.5:
        df_min = 0.5
    params['delta_f'] = df_min
    hp, hc = get_fd_waveform(**params)
    hp = hp.astype(dtype)
    if return_hc:
        hc = hc.astype(dtype)
    else:
        hc = None

    f_end = get_waveform_end_frequency(**params)
    if f_end is None:
        f_end = (len(hp) - 1) * hp.delta_f
    if 'f_final' in params and params['f_final'] > 0:
        f_end_params = params['f_final']
        if f_end is not None:
            f_end = min(f_end_params, f_end)

    n_min = int(rulog2(f_end / df_min)) + 1
    if n_min < len(hp):
        hp = hp[:n_min]
        if hc is not None:
            hc = hc[:n_min]

    offset = int(ringdown_padding * (len(hp)-1)*2 * hp.delta_f)

    hp = interpolate_complex_frequency(hp, df, zeros_offset=offset, side='left')
    if hc is not None:
        hc = interpolate_complex_frequency(hc, df, zeros_offset=offset,
                                           side='left')
    params['approximant'] = orig_approx
    return hp, hc

def get_sgburst_waveform(template=None, **kwargs):
    """Return the plus and cross polarizations of a time domain
    sine-Gaussian burst waveform.

    Parameters
    ----------
    template: object
        An object that has attached properties. This can be used to subsitute
        for keyword arguments. A common example would be a row in an xml table.
    approximant : string
        A string that indicates the chosen approximant. See `td_approximants`
        for available options.
    q : float
        The quality factor of a sine-Gaussian burst
    frequency : float
        The centre-frequency of a sine-Gaussian burst
    delta_t : float
        The time step used to generate the waveform
    hrss : float
        The strain rss
    amplitude: float
        The strain amplitude

    Returns
    -------
    hplus: TimeSeries
        The plus polarization of the waveform.
    hcross: TimeSeries
        The cross polarization of the waveform.
    """
    input_params = props_sgburst(template,**kwargs)

    for arg in sgburst_required_args:
        if arg not in input_params:
            raise ValueError("Please provide " + str(arg))

    return _lalsim_sgburst_waveform(**input_params)

# Waveform filter routines ###################################################

# Organize Filter Generators
_inspiral_fd_filters = {}
_cuda_fd_filters = {}

_cuda_fd_filters['SPAtmplt'] = spa_tmplt
_inspiral_fd_filters['SPAtmplt'] = spa_tmplt

filter_wav = _scheme.ChooseBySchemeDict()
filter_wav.update( {_scheme.CPUScheme:_inspiral_fd_filters,
                    _scheme.CUDAScheme:_cuda_fd_filters,
                   } )

# Organize functions for function conditioning/precalculated values
_filter_norms = {}
_filter_ends = {}
_filter_preconditions = {}
_template_amplitude_norms = {}
_filter_time_lengths = {}

def seobnrv2_final_frequency(**kwds):
    return pnutils.get_final_freq("SEOBNRv2", kwds['mass1'], kwds['mass2'],
                                  kwds['spin1z'], kwds['spin2z'])

def get_imr_length(approx, **kwds):
    """Call through to pnutils to obtain IMR waveform durations
    """
    m1 = float(kwds['mass1'])
    m2 = float(kwds['mass2'])
    s1z = float(kwds['spin1z'])
    s2z = float(kwds['spin2z'])
    f_low = float(kwds['f_lower'])
    # 10% margin of error is incorporated in the pnutils function
    return pnutils.get_imr_duration(m1, m2, s1z, s2z, f_low, approximant=approx)

def seobnrv2_length_in_time(**kwds):
    """Stub for holding the calculation of SEOBNRv2* waveform duration.
    """
    return get_imr_length("SEOBNRv2", **kwds)

def seobnrv4_length_in_time(**kwds):
    """Stub for holding the calculation of SEOBNRv4* waveform duration.
    """
    return get_imr_length("SEOBNRv4", **kwds)

def seobnrv5_length_in_time(**kwds):
    """Stub for holding the calculation of SEOBNRv5_ROM waveform duration.
    """
    return get_imr_length("SEOBNRv5_ROM", **kwds)

def imrphenomd_length_in_time(**kwds):
    """Stub for holding the calculation of IMRPhenomD waveform duration.
    """
    return get_imr_length("IMRPhenomD", **kwds)

def imrphenomhm_length_in_time(**kwargs):
    """Estimates the duration of IMRPhenom waveforms that include higher modes.
    """
    # Default maximum node number for IMRPhenomHM is 4
    # The relevant lower order approximant here is IMRPhenomD
    return get_hm_length_in_time("IMRPhenomD", 4, **kwargs)

def seobnrv4hm_length_in_time(**kwargs):
    """ Estimates the duration of SEOBNRv4HM waveforms that include higher modes.
    """
    # Default maximum node number for SEOBNRv4HM is 5
    # The relevant lower order approximant here is SEOBNRv4
    return get_hm_length_in_time('SEOBNRv4', 5, **kwargs)

def get_hm_length_in_time(lor_approx, maxm_default, **kwargs):
    kwargs = parse_mode_array(kwargs)
    if 'mode_array' in kwargs and kwargs['mode_array'] is not None:
        maxm = max(m for _, m in kwargs['mode_array'])
    else:
        maxm = maxm_default
    try:
        flow = kwargs['f_lower']
    except KeyError:
        raise ValueError("must provide a f_lower")
    kwargs['f_lower'] = flow * 2./maxm
    return get_imr_length(lor_approx, **kwargs)

_filter_norms["SPAtmplt"] = spa_tmplt_norm
_filter_preconditions["SPAtmplt"] = spa_tmplt_precondition

_filter_ends["SPAtmplt"] = spa_tmplt_end
_filter_ends["TaylorF2"] = spa_tmplt_end
_filter_ends["TaylorF2Ecc"] = spa_tmplt_end
#_filter_ends["SEOBNRv1_ROM_EffectiveSpin"] = seobnrv2_final_frequency
#_filter_ends["SEOBNRv1_ROM_DoubleSpin"] =  seobnrv2_final_frequency
#_filter_ends["SEOBNRv2_ROM_EffectiveSpin"] = seobnrv2_final_frequency
#_filter_ends["SEOBNRv2_ROM_DoubleSpin"] =  seobnrv2_final_frequency
#_filter_ends["SEOBNRv2_ROM_DoubleSpin_HI"] = seobnrv2_final_frequency
# PhenomD returns higher frequencies than this, so commenting this out for now
#_filter_ends["IMRPhenomC"] = seobnrv2_final_frequency
#_filter_ends["IMRPhenomD"] = seobnrv2_final_frequency

_template_amplitude_norms["SPAtmplt"] = spa_amplitude_factor
_filter_time_lengths["SPAtmplt"] = spa_length_in_time
_filter_time_lengths["TaylorF2"] = spa_length_in_time
_filter_time_lengths["TaylorF2Ecc"] = spa_length_in_time
_filter_time_lengths["SpinTaylorT5"] = spa_length_in_time
_filter_time_lengths["SEOBNRv1_ROM_EffectiveSpin"] = seobnrv2_length_in_time
_filter_time_lengths["SEOBNRv1_ROM_DoubleSpin"] = seobnrv2_length_in_time
_filter_time_lengths["SEOBNRv2_ROM_EffectiveSpin"] = seobnrv2_length_in_time
_filter_time_lengths["SEOBNRv2_ROM_DoubleSpin"] = seobnrv2_length_in_time
_filter_time_lengths["EOBNRv2_ROM"] = seobnrv2_length_in_time
_filter_time_lengths["EOBNRv2HM_ROM"] = seobnrv2_length_in_time
_filter_time_lengths["SEOBNRv2_ROM_DoubleSpin_HI"] = seobnrv2_length_in_time
_filter_time_lengths["SEOBNRv4_ROM"] = seobnrv4_length_in_time
_filter_time_lengths["SEOBNRv4HM_ROM"] = seobnrv4hm_length_in_time
_filter_time_lengths["SEOBNRv4"] = seobnrv4_length_in_time
_filter_time_lengths["SEOBNRv4P"] = seobnrv4_length_in_time
_filter_time_lengths["SEOBNRv5_ROM"] = seobnrv5_length_in_time
_filter_time_lengths["IMRPhenomC"] = imrphenomd_length_in_time
_filter_time_lengths["IMRPhenomD"] = imrphenomd_length_in_time
_filter_time_lengths["IMRPhenomPv2"] = imrphenomd_length_in_time
_filter_time_lengths["IMRPhenomD_NRTidal"] = imrphenomd_length_in_time
_filter_time_lengths["IMRPhenomPv2_NRTidal"] = imrphenomd_length_in_time
_filter_time_lengths["IMRPhenomHM"] = imrphenomhm_length_in_time
_filter_time_lengths["IMRPhenomPv3HM"] = imrphenomhm_length_in_time
_filter_time_lengths["IMRPhenomXHM"] = imrphenomhm_length_in_time
_filter_time_lengths["IMRPhenomXPHM"] = imrphenomhm_length_in_time
_filter_time_lengths["SpinTaylorF2"] = spa_length_in_time
_filter_time_lengths["TaylorF2NL"] = spa_length_in_time
_filter_time_lengths["PreTaylorF2"] = spa_length_in_time

# Also add generators for switching between approximants
apx_name = "SpinTaylorF2_SWAPPER"
cpu_fd[apx_name] =  _spintaylor_aligned_prec_swapper
_filter_time_lengths[apx_name] = _filter_time_lengths["SpinTaylorF2"]

from . nltides import nonlinear_tidal_spa
cpu_fd["TaylorF2NL"] = nonlinear_tidal_spa

from .premerger import premerger_taylorf2
cpu_fd['PreTaylorF2'] = premerger_taylorf2

from .multiband import multiband_fd_waveform
cpu_fd['multiband'] = multiband_fd_waveform

# Load external waveforms #####################################################
if 'PYCBC_WAVEFORM' in os.environ:
    mods = os.environ['PYCBC_WAVEFORM'].split(':')
    for mod in mods:
        mhandle = __import__(mod, fromlist=[''])
        mhandle.add_me(cpu_fd=cpu_fd,
                       cpu_td=cpu_td,
                       filter_time_lengths=_filter_time_lengths)

def td_fd_waveform_transform(approximant):
    '''If the waveform approximant is in time domain, make a frequency domain
    version using 'get_fd_waveform_from_td'; If the waveform approximant is in
    frequency domain, do interpolation for waveforms with a time length estimator,
    and make a time domain version using 'get_td_waveform_from_fd'

    Parameters
    ----------
    approximant: string
        The name of a waveform approximant.
    '''
    fd_apx = list(cpu_fd.keys())
    td_apx = list(cpu_td.keys())

    if (approximant in td_apx) and (approximant not in fd_apx):
        # We can make a fd version of td approximants
        cpu_fd[approximant] = get_fd_waveform_from_td

    if approximant in fd_apx:
        # We can do interpolation for waveforms that have a time length
        apx_int = approximant + '_INTERP'
        cpu_fd[apx_int] = get_interpolated_fd_waveform
        _filter_time_lengths[apx_int] = _filter_time_lengths[approximant]

        # We can also make a td version of this
        # This will override any existing approximants with the same name
        # (ex. IMRPhenomXX)
        if approximant not in td_apx:
            cpu_td[approximant] = get_td_waveform_from_fd

for apx in copy.copy(_filter_time_lengths):
    td_fd_waveform_transform(apx)


td_wav = _scheme.ChooseBySchemeDict()
fd_wav = _scheme.ChooseBySchemeDict()
td_wav.update({_scheme.CPUScheme:cpu_td,_scheme.CUDAScheme:cuda_td})
fd_wav.update({_scheme.CPUScheme:cpu_fd,_scheme.CUDAScheme:cuda_fd})
sgburst_wav = {_scheme.CPUScheme:cpu_sgburst}

def get_waveform_filter(out, template=None, **kwargs):
    """Return a frequency domain waveform filter for the specified approximant
    """
    n = len(out)

    input_params = props(template, **kwargs)

    if input_params['approximant'] in filter_approximants(_scheme.mgr.state):
        wav_gen = filter_wav[type(_scheme.mgr.state)]
        htilde = wav_gen[input_params['approximant']](out=out, **input_params)
        htilde.resize(n)
        htilde.chirp_length = get_waveform_filter_length_in_time(**input_params)
        htilde.length_in_time = htilde.chirp_length
        return htilde

    if input_params['approximant'] in fd_approximants(_scheme.mgr.state):
        wav_gen = fd_wav[type(_scheme.mgr.state)]

        duration = get_waveform_filter_length_in_time(**input_params)
        hp, _ = wav_gen[input_params['approximant']](duration=duration,
                                               return_hc=False, **input_params)

        hp.resize(n)
        out[0:len(hp)] = hp[:]
        hp.data = out

        hp.length_in_time = hp.chirp_length = duration
        return hp

    elif input_params['approximant'] in td_approximants(_scheme.mgr.state):
        wav_gen = td_wav[type(_scheme.mgr.state)]
        hp, _ = wav_gen[input_params['approximant']](**input_params)
        # taper the time series hp if required
        if 'taper' in input_params.keys() and \
                input_params['taper'] is not None:
            hp = wfutils.taper_timeseries(hp, input_params['taper'],
                                          return_lal=False)
        return td_waveform_to_fd_waveform(hp, out=out)

    else:
        raise ValueError("Approximant %s not available" %
                            (input_params['approximant']))

def td_waveform_to_fd_waveform(waveform, out=None, length=None,
                               buffer_length=100):
    """ Convert a time domain into a frequency domain waveform by FFT.
        As a waveform is assumed to "wrap" in the time domain one must be
        careful to ensure the waveform goes to 0 at both "boundaries". To
        ensure this is done correctly the waveform must have the epoch set such
        the merger time is at t=0 and the length of the waveform should be
        shorter than the desired length of the FrequencySeries (times 2 - 1)
        so that zeroes can be suitably pre- and post-pended before FFTing.
        If given, out is a memory array to be used as the output of the FFT.
        If not given memory is allocated internally.
        If present the length of the returned FrequencySeries is determined
        from the length out. If out is not given the length can be provided
        expicitly, or it will be chosen as the nearest power of 2. If choosing
        length explicitly the waveform length + buffer_length is used when
        choosing the nearest binary number so that some zero padding is always
        added.
    """
    # Figure out lengths and set out if needed
    if out is None:
        if length is None:
            N = pnutils.nearest_larger_binary_number(len(waveform) + \
                                                     buffer_length)
            n = int(N//2) + 1
        else:
            n = length
            N = (n-1)*2
        out = zeros(n, dtype=complex_same_precision_as(waveform))
    else:
        n = len(out)
        N = (n-1)*2
    delta_f =  1. / (N * waveform.delta_t)

    # total duration of the waveform
    tmplt_length = len(waveform) * waveform.delta_t
    if len(waveform) > N:
        err_msg = "The time domain template is longer than the intended "
        err_msg += "duration in the frequency domain. This situation is "
        err_msg += "not supported in this function. Please shorten the "
        err_msg += "waveform appropriately before calling this function or "
        err_msg += "increase the allowed waveform length. "
        err_msg += "Waveform length (in samples): {}".format(len(waveform))
        err_msg += ". Intended length: {}.".format(N)
        raise ValueError(err_msg)
    # for IMR templates the zero of time is at max amplitude (merger)
    # thus the start time is minus the duration of the template from
    # lower frequency cutoff to merger, i.e. minus the 'chirp time'
    tChirp = - float( waveform.start_time )  # conversion from LIGOTimeGPS
    waveform.resize(N)
    k_zero = int(waveform.start_time / waveform.delta_t)
    waveform.roll(k_zero)
    htilde = FrequencySeries(out, delta_f=delta_f, copy=False)
    fft(waveform.astype(real_same_precision_as(htilde)), htilde)
    htilde.length_in_time = tmplt_length
    htilde.chirp_length = tChirp
    return htilde

def get_two_pol_waveform_filter(outplus, outcross, template, **kwargs):
    """Return a frequency domain waveform filter for the specified approximant.
    Unlike get_waveform_filter this function returns both h_plus and h_cross
    components of the waveform, which are needed for searches where h_plus
    and h_cross are not related by a simple phase shift.
    """
    n = len(outplus)

    # If we don't have an inclination column alpha3 might be used
    if not hasattr(template, 'inclination') and 'inclination' not in kwargs:
        if hasattr(template, 'alpha3'):
            kwargs['inclination'] = template.alpha3

    input_params = props(template, **kwargs)

    if input_params['approximant'] in fd_approximants(_scheme.mgr.state):
        wav_gen = fd_wav[type(_scheme.mgr.state)]
        hp, hc = wav_gen[input_params['approximant']](**input_params)
        hp.resize(n)
        hc.resize(n)
        outplus[0:len(hp)] = hp[:]
        hp = FrequencySeries(outplus, delta_f=hp.delta_f, copy=False)
        outcross[0:len(hc)] = hc[:]
        hc = FrequencySeries(outcross, delta_f=hc.delta_f, copy=False)
        hp.chirp_length = get_waveform_filter_length_in_time(**input_params)
        hp.length_in_time = hp.chirp_length
        hc.chirp_length = hp.chirp_length
        hc.length_in_time = hp.length_in_time
        return hp, hc
    elif input_params['approximant'] in td_approximants(_scheme.mgr.state):
        # N: number of time samples required
        N = (n-1)*2
        delta_f = 1.0 / (N * input_params['delta_t'])
        wav_gen = td_wav[type(_scheme.mgr.state)]
        hp, hc = wav_gen[input_params['approximant']](**input_params)
        # taper the time series hp if required
        if 'taper' in input_params.keys() and \
                input_params['taper'] is not None:
            hp = wfutils.taper_timeseries(hp, input_params['taper'],
                                          return_lal=False)
            hc = wfutils.taper_timeseries(hc, input_params['taper'],
                                          return_lal=False)
        # total duration of the waveform
        tmplt_length = len(hp) * hp.delta_t
        # for IMR templates the zero of time is at max amplitude (merger)
        # thus the start time is minus the duration of the template from
        # lower frequency cutoff to merger, i.e. minus the 'chirp time'
        tChirp = - float( hp.start_time )  # conversion from LIGOTimeGPS
        hp.resize(N)
        hc.resize(N)
        k_zero = int(hp.start_time / hp.delta_t)
        hp.roll(k_zero)
        hc.roll(k_zero)
        hp_tilde = FrequencySeries(outplus, delta_f=delta_f, copy=False)
        hc_tilde = FrequencySeries(outcross, delta_f=delta_f, copy=False)
        fft(hp.astype(real_same_precision_as(hp_tilde)), hp_tilde)
        fft(hc.astype(real_same_precision_as(hc_tilde)), hc_tilde)
        hp_tilde.length_in_time = tmplt_length
        hp_tilde.chirp_length = tChirp
        hc_tilde.length_in_time = tmplt_length
        hc_tilde.chirp_length = tChirp
        return hp_tilde, hc_tilde
    else:
        raise ValueError("Approximant %s not available" %
                            (input_params['approximant']))

def waveform_norm_exists(approximant):
    if approximant in _filter_norms:
        return True
    else:
        return False

def get_template_amplitude_norm(template=None, **kwargs):
    """ Return additional constant template normalization. This only affects
        the effective distance calculation. Returns None for all templates with a
        physically meaningful amplitude.
    """
    input_params = props(template,**kwargs)
    approximant = kwargs['approximant']

    if approximant in _template_amplitude_norms:
        return _template_amplitude_norms[approximant](**input_params)
    else:
        return None

def get_waveform_filter_precondition(approximant, length, delta_f):
    """Return the data preconditioning factor for this approximant.
    """
    if approximant in _filter_preconditions:
        return _filter_preconditions[approximant](length, delta_f)
    else:
        return None

def get_waveform_filter_norm(approximant, psd, length, delta_f, f_lower):
    """ Return the normalization vector for the approximant
    """
    if approximant in _filter_norms:
        return _filter_norms[approximant](psd, length, delta_f, f_lower)
    else:
        return None

def get_waveform_end_frequency(template=None, **kwargs):
    """Return the stop frequency of a template
    """
    input_params = props(template,**kwargs)
    approximant = kwargs['approximant']

    if approximant in _filter_ends:
        return _filter_ends[approximant](**input_params)
    else:
        return None

def get_waveform_filter_length_in_time(approximant, template=None, **kwargs):
    """For filter templates, return the length in time of the template.
    """
    kwargs = props(template, **kwargs)

    if approximant in _filter_time_lengths:
        return _filter_time_lengths[approximant](**kwargs)
    else:
        return None

__all__ = ["get_td_waveform", "get_td_det_waveform_from_fd_det",
           "get_fd_waveform", "get_fd_waveform_sequence",
           "get_fd_det_waveform", "get_fd_det_waveform_sequence",
           "get_fd_waveform_from_td",
           "print_td_approximants", "print_fd_approximants",
           "td_approximants", "fd_approximants",
           "get_waveform_filter", "filter_approximants",
           "get_waveform_filter_norm", "get_waveform_end_frequency",
           "waveform_norm_exists", "get_template_amplitude_norm",
           "get_waveform_filter_length_in_time", "get_sgburst_waveform",
           "print_sgburst_approximants", "sgburst_approximants",
           "td_waveform_to_fd_waveform", "get_two_pol_waveform_filter",
           "NoWaveformError", "FailedWaveformError", "get_td_waveform_from_fd",
           'cpu_fd', 'cpu_td', 'fd_sequence', 'fd_det_sequence', 'fd_det',
           '_filter_time_lengths']
