"""
Exp 9 -- Generalised Driving-Cycle Distance Correction
=========================================================================

Fully general per-event formulation for the distance-correction method.

A "deceleration-acceleration event" is defined by three speeds:
    v_entry  -->  v_low  -->  v_exit

The old code (v1) assumed every event was a symmetric full-stop cycle
(v_c -> 0 -> v_c) and used a fixed Delta_s per stop.  This version
derives the correction for arbitrary (v_entry, v_low, v_exit) tuples,
including asymmetric events and partial decelerations.

=========================================================================
KEY FORMULA
=========================================================================

For event i that replaces s_event_i metres of cruise at v_cruise:

    Delta_s_i  =  dE_i / e_ref

where:
    dE_i   = E_event_i  -  e_cruise * s_event_i    (net energy change, J)
    e_ref  = E_0 / d                                (baseline trip-average rate, J/m)
    e_cruise = (F_rr + F_aero(v_cruise)) / eta_dt   (cruise energy rate, J/m)

    E_event_i is the battery-side energy consumed during the event.
    s_event_i is the physical distance traversed during the event.

For the full trip:
    d_corrected  = d + sum_i Delta_s_i
    EP_corrected = E_total / d_corrected

When all events are symmetric (v_entry = v_exit = v_cruise), the
transition energy is zero and the formula reduces to the closed-form
expression from v1.

=========================================================================
"""
from __future__ import annotations
import sys
import pathlib
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from typing import List, Tuple, Optional

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'simulation'))
from models.vehicle_physics import (
    compute_ep, BASELINE, apply_style, eta_bat,
    FIG_W, FIG_H, DPI, FS_LEGEND, FS_LABEL, FS_TITLE, FS_TICK,
    FIT_LW, FIT_ALPHA, GRID_ALPHA,
)

_J_TO_KWH = 1.0 / 3_600_000.0

RESULTS_DIR   = ROOT / 'simulation' / 'results'
RESULTS_FIG   = RESULTS_DIR / 'figures' / 'exp9_distance_correction.png'
RESULTS_FIG2  = RESULTS_DIR / 'figures' / 'exp9_asymmetric_events.png'
RESULTS_FIG3  = RESULTS_DIR / 'figures' / 'exp9_mixed_trip.png'
RESULTS_FIG4  = RESULTS_DIR / 'figures' / 'exp9_regen_sweep.png'
RESULTS_TABLE = RESULTS_DIR / 'tables'  / 'exp9_distance_correction.csv'


# ======================================================================
# 1. Per-event energy and distance
# ======================================================================

def compute_event_energy(
    v_entry: float,
    v_low: float,
    v_exit: float,
    m: float,
    a_acc: float   = BASELINE['a_acc'],
    a_dec: float   = BASELINE['a_dec'],
    crr: float     = BASELINE['crr'],
    cda: float     = BASELINE['cda'],
    rho: float     = BASELINE['rho'],
    eta_dt: float  = BASELINE['eta_dt'],
    eta_regen: float = BASELINE['eta_regen'],
    g: float       = BASELINE['g'],
) -> dict:
    """
    Energy and distance for a single event: v_entry -> v_low -> v_exit.

    Deceleration phase: v_entry -> v_low  (vehicle brakes)
    Acceleration phase: v_low   -> v_exit (vehicle accelerates)

    Aerodynamic drag during acc/dec uses the average speed of each phase,
    consistent with compute_ep().

    Returns dict with distances, energies, and forces.
    """
    F_rr = crr * m * g

    # -- Deceleration phase --
    s_dec = (v_entry**2 - v_low**2) / (2.0 * a_dec) if v_entry > v_low else 0.0
    v_avg_dec = (v_entry + v_low) / 2.0
    F_aero_dec = 0.5 * rho * cda * v_avg_dec**2

    KE_entry = 0.5 * m * v_entry**2
    KE_low   = 0.5 * m * v_low**2

    # Mechanical energy available for regen = KE lost - road drag work
    regen_mech = (KE_entry - KE_low) - (F_rr + F_aero_dec) * s_dec
    E_regen = eta_regen * max(0.0, regen_mech)  # energy returned TO battery

    # -- Acceleration phase --
    s_acc = (v_exit**2 - v_low**2) / (2.0 * a_acc) if v_exit > v_low else 0.0
    v_avg_acc = (v_low + v_exit) / 2.0
    F_aero_acc = 0.5 * rho * cda * v_avg_acc**2

    KE_exit = 0.5 * m * v_exit**2

    # Battery energy consumed = (KE gain + road drag) / eta_dt
    E_acc = ((KE_exit - KE_low) + (F_rr + F_aero_acc) * s_acc) / eta_dt

    # Total event
    s_event = s_dec + s_acc
    E_event = E_acc - E_regen   # E_acc > 0, E_regen >= 0

    return dict(
        s_dec=s_dec, s_acc=s_acc, s_event=s_event,
        E_acc=E_acc, E_regen=E_regen, E_event=E_event,
        KE_entry=KE_entry, KE_low=KE_low, KE_exit=KE_exit,
        F_rr=F_rr, F_aero_dec=F_aero_dec, F_aero_acc=F_aero_acc,
        regen_mech=max(0.0, regen_mech),
    )


def cruise_energy_rate(
    v_ref: float, m: float,
    crr: float = BASELINE['crr'], cda: float = BASELINE['cda'],
    rho: float = BASELINE['rho'], eta_dt: float = BASELINE['eta_dt'],
    g: float = BASELINE['g'],
) -> float:
    """Battery-side energy per metre at constant v_ref (J/m)."""
    return (crr * m * g + 0.5 * rho * cda * v_ref**2) / eta_dt


# ======================================================================
# 2. Flexible trip simulator
# ======================================================================

def simulate_trip(
    events: List[Tuple[float, float, float]],
    m: float,
    v_cruise: float  = BASELINE['v_c'],
    d_total: float   = BASELINE['d_total'],
    crr: float       = BASELINE['crr'],
    cda: float       = BASELINE['cda'],
    rho: float       = BASELINE['rho'],
    eta_dt: float    = BASELINE['eta_dt'],
    eta_regen: float = BASELINE['eta_regen'],
    T_amb: float     = 20.0,
    g: float         = BASELINE['g'],
) -> dict:
    """
    Simulate a complete trip with arbitrary deceleration-acceleration events.

    Trip structure:
        [0 -> v_c] + cruise + [event_1] + cruise + ... + [v_c -> 0]

    If an event has v_exit != v_cruise (or next event v_entry != v_cruise),
    a speed transition segment is automatically inserted.

    The energy accounting exactly matches compute_ep() for the special
    case of n identical full-stop symmetric events.
    """
    kw = dict(m=m, crr=crr, cda=cda, rho=rho, eta_dt=eta_dt,
              eta_regen=eta_regen, g=g)

    e_cruise = cruise_energy_rate(v_cruise, m, crr=crr, cda=cda,
                                  rho=rho, eta_dt=eta_dt, g=g)

    # Initial acceleration 0 -> v_cruise
    ev_init = compute_event_energy(0.0, 0.0, v_cruise, **kw)
    d_init, E_init = ev_init['s_acc'], ev_init['E_acc']

    # Final deceleration v_cruise -> 0
    ev_final = compute_event_energy(v_cruise, 0.0, 0.0, **kw)
    d_final = ev_final['s_dec']
    E_final = -ev_final['E_regen']  # negative = returned to battery

    # Process events + transitions
    d_ev = 0.0; E_ev = 0.0
    d_tr = 0.0; E_tr = 0.0
    ev_details = []
    prev_v = v_cruise

    for v_in, v_lo, v_out in events:
        # Transition to v_in if needed
        if abs(prev_v - v_in) > 0.01:
            if prev_v > v_in:
                tr = compute_event_energy(prev_v, v_in, v_in, **kw)
                d_tr += tr['s_dec']; E_tr += -tr['E_regen']
            else:
                tr = compute_event_energy(prev_v, prev_v, v_in, **kw)
                d_tr += tr['s_acc']; E_tr += tr['E_acc']

        ev = compute_event_energy(v_in, v_lo, v_out, **kw)
        d_ev += ev['s_event']; E_ev += ev['E_event']
        ev_details.append(ev)
        prev_v = v_out

    # Transition back to v_cruise if needed
    if abs(prev_v - v_cruise) > 0.01:
        if prev_v > v_cruise:
            tr = compute_event_energy(prev_v, v_cruise, v_cruise, **kw)
            d_tr += tr['s_dec']; E_tr += -tr['E_regen']
        else:
            tr = compute_event_energy(prev_v, prev_v, v_cruise, **kw)
            d_tr += tr['s_acc']; E_tr += tr['E_acc']

    d_cruise_seg = d_total - d_init - d_final - d_ev - d_tr
    if d_cruise_seg < 0:
        raise ValueError(
            f"Events too many/long: non-cruise distance "
            f"= {d_total - d_cruise_seg:.0f} m > d_total = {d_total:.0f} m."
        )
    E_cruise_seg = e_cruise * d_cruise_seg

    E_mech = E_init + E_cruise_seg + E_ev + E_final + E_tr
    _eb = eta_bat(T_amb)
    E_bat = E_mech / _eb
    EP = (E_bat * _J_TO_KWH) / (d_total / 1000.0)

    return dict(
        EP=EP, E_bat_kWh=E_bat * _J_TO_KWH, E_bat_J=E_bat,
        E_mech_J=E_mech, E_cruise_J=E_cruise_seg,
        E_init_J=E_init, E_final_J=E_final,
        E_events_J=E_ev, E_trans_J=E_tr,
        d_cruise=d_cruise_seg, d_events=d_ev,
        d_init=d_init, d_final=d_final, d_trans=d_tr,
        e_cruise=e_cruise, eta_bat_val=_eb,
        event_details=ev_details,
    )


# ======================================================================
# 3. Distance-correction computation
# ======================================================================

def compute_delta_s(
    events: List[Tuple[float, float, float]],
    m: float,
    v_cruise: float  = BASELINE['v_c'],
    d_total: float   = BASELINE['d_total'],
    **kwargs,
) -> dict:
    """
    Compute the per-event and total distance correction.

    For symmetric events (v_entry = v_exit = v_cruise), the formula is:
        Delta_s_i = (E_event_i - e_cruise * s_event_i) / e_ref

    For asymmetric events, the event energy and distance include only
    the v_entry->v_low->v_exit segment.  Any speed transitions between
    v_exit and the next cruise (or between cruise and v_entry) contribute
    additional corrections that are computed separately.

    The method uses e_ref = E_mech_0 / d_total (the baseline trip's
    mechanical energy per metre, before eta_bat).  This choice ensures
    that eta_dt and eta_bat cancel exactly.

    Returns a dict with EP_sim, EP_0, EP_corrected, per-event details, etc.
    """
    kw_trip = dict(m=m, v_cruise=v_cruise, d_total=d_total, **kwargs)

    trip_with = simulate_trip(events, **kw_trip)
    trip_base = simulate_trip([], **kw_trip)

    EP_0      = trip_base['EP']
    E_bat_kwh = trip_with['E_bat_kWh']

    # Reference rates (before eta_bat -- it cancels)
    e_ref    = trip_base['E_mech_J'] / d_total   # J/m
    e_cruise = trip_base['e_cruise']              # J/m

    kw_ev = dict(m=m, **{k: v for k, v in kwargs.items()
                         if k in ('crr','cda','rho','eta_dt','eta_regen','g',
                                  'a_acc','a_dec')})

    # -- Per-event Delta_s (for symmetric events at v_cruise) --
    ev_results = []
    for v_in, v_lo, v_out in events:
        ev = compute_event_energy(v_in, v_lo, v_out, **kw_ev)
        # Energy CHANGE relative to cruise that this event displaces
        dE_i = ev['E_event'] - e_cruise * ev['s_event']
        ds_i = dE_i / e_ref
        ev['dE_i']    = dE_i
        ev['delta_s'] = ds_i
        ev_results.append(ev)

    sum_ds_events = sum(e['delta_s'] for e in ev_results)

    # -- Transition corrections --
    # When events have v_exit != v_cruise (or v_entry != v_cruise),
    # the trip simulator inserts transition segments.  These also
    # displace cruise distance.  We compute their Delta_s too.
    prev_v = v_cruise
    tr_corrections = []
    for v_in, v_lo, v_out in events:
        if abs(prev_v - v_in) > 0.01:
            if prev_v > v_in:
                tr = compute_event_energy(prev_v, v_in, v_in, **kw_ev)
                E_tr = -tr['E_regen']; s_tr = tr['s_dec']
            else:
                tr = compute_event_energy(prev_v, prev_v, v_in, **kw_ev)
                E_tr = tr['E_acc']; s_tr = tr['s_acc']
            dE_tr = E_tr - e_cruise * s_tr
            ds_tr = dE_tr / e_ref
            tr_corrections.append(dict(
                from_v=prev_v, to_v=v_in,
                s=s_tr, E=E_tr, dE=dE_tr, delta_s=ds_tr,
            ))
        prev_v = v_out

    # Final transition back to v_cruise
    if abs(prev_v - v_cruise) > 0.01:
        if prev_v > v_cruise:
            tr = compute_event_energy(prev_v, v_cruise, v_cruise, **kw_ev)
            E_tr = -tr['E_regen']; s_tr = tr['s_dec']
        else:
            tr = compute_event_energy(prev_v, prev_v, v_cruise, **kw_ev)
            E_tr = tr['E_acc']; s_tr = tr['s_acc']
        dE_tr = E_tr - e_cruise * s_tr
        ds_tr = dE_tr / e_ref
        tr_corrections.append(dict(
            from_v=prev_v, to_v=v_cruise,
            s=s_tr, E=E_tr, dE=dE_tr, delta_s=ds_tr,
        ))

    sum_ds_trans = sum(t['delta_s'] for t in tr_corrections)
    total_ds     = sum_ds_events + sum_ds_trans

    # Corrected EP
    d_corr_m  = d_total + total_ds
    d_corr_km = d_corr_m / 1000.0
    EP_corr   = E_bat_kwh / d_corr_km
    err_pct   = (EP_corr - EP_0) / EP_0 * 100.0 if EP_0 > 0 else 0.0

    # Also: cruise-based reference for comparison
    ev_results_cruise = []
    for v_in, v_lo, v_out in events:
        ev = compute_event_energy(v_in, v_lo, v_out, **kw_ev)
        dE_c = ev['E_event'] - e_cruise * ev['s_event']
        ds_c = dE_c / e_cruise   # using cruise as denominator
        ev_results_cruise.append(ds_c)
    sum_ds_cruise_ev = sum(ev_results_cruise)
    # (transitions also need recalculating with e_cruise as denominator,
    #  but for simplicity we recompute total)
    prev_v = v_cruise
    sum_ds_cruise_tr = 0.0
    for v_in, v_lo, v_out in events:
        if abs(prev_v - v_in) > 0.01:
            if prev_v > v_in:
                tr = compute_event_energy(prev_v, v_in, v_in, **kw_ev)
                E_tr = -tr['E_regen']; s_tr = tr['s_dec']
            else:
                tr = compute_event_energy(prev_v, prev_v, v_in, **kw_ev)
                E_tr = tr['E_acc']; s_tr = tr['s_acc']
            sum_ds_cruise_tr += (E_tr - e_cruise * s_tr) / e_cruise
        prev_v = v_out
    if abs(prev_v - v_cruise) > 0.01:
        if prev_v > v_cruise:
            tr = compute_event_energy(prev_v, v_cruise, v_cruise, **kw_ev)
            E_tr = -tr['E_regen']; s_tr = tr['s_dec']
        else:
            tr = compute_event_energy(prev_v, prev_v, v_cruise, **kw_ev)
            E_tr = tr['E_acc']; s_tr = tr['s_acc']
        sum_ds_cruise_tr += (E_tr - e_cruise * s_tr) / e_cruise

    total_ds_cruise = sum_ds_cruise_ev + sum_ds_cruise_tr
    d_corr_cruise   = d_total + total_ds_cruise
    EP_corr_cruise  = E_bat_kwh / (d_corr_cruise / 1000.0)
    err_cruise      = (EP_corr_cruise - EP_0) / EP_0 * 100.0 if EP_0 > 0 else 0.0

    return dict(
        EP_sim         = trip_with['EP'],
        EP_0           = EP_0,
        EP_corr_avg    = EP_corr,
        EP_corr_cruise = EP_corr_cruise,
        err_avg_pct    = err_pct,
        err_cruise_pct = err_cruise,
        E_bat_kWh      = E_bat_kwh,
        d_corr_avg_km  = d_corr_km,
        d_corr_cruise_km = d_corr_cruise / 1000.0,
        total_ds_avg   = total_ds,
        total_ds_cruise = total_ds_cruise,
        sum_ds_events  = sum_ds_events,
        sum_ds_trans   = sum_ds_trans,
        ev_results     = ev_results,
        tr_corrections = tr_corrections,
        e_ref          = e_ref,
        e_cruise       = e_cruise,
    )


# ======================================================================
# 4. Main experiment
# ======================================================================

def run() -> dict:
    """Run all Exp 9 sub-experiments."""
    m   = BASELINE['m']
    v_c = BASELINE['v_c']
    d   = BASELINE['d_total']

    print('=' * 70)
    print('Exp 9 -- Generalised Driving-Cycle Distance Correction')
    print('=' * 70)

    # ==================================================================
    # A: Symmetric sweep  v_c -> v_low -> v_c
    # ==================================================================
    print('\n--- Phase A: Symmetric Event Sweep ---\n')

    v_low_kmh = [0, 10, 20, 30, 40, 50, 60, 70, 80]
    sym_rows = []

    for eta_r in [0.0, 0.90]:
        print(f'  [eta_regen = {eta_r:.2f}]')
        hdr = (f'    {"v_low":>6}  {"s_ev":>7}  {"E_ev":>9}  '
               f'{"ds(avg)":>10}  {"ds(crs)":>10}  '
               f'{"err_avg":>10}  {"err_crs":>10}')
        print(hdr)
        print('    ' + '-' * (len(hdr) - 4))

        for vl_kmh in v_low_kmh:
            vl = vl_kmh / 3.6
            res = compute_delta_s(
                [(v_c, vl, v_c)], m=m, v_cruise=v_c, d_total=d,
                eta_regen=eta_r)
            ev = res['ev_results'][0]
            print(f'    {vl_kmh:>4d} km/h  {ev["s_event"]:>7.1f}  '
                  f'{ev["E_event"]*_J_TO_KWH:>9.4f}  '
                  f'{res["total_ds_avg"]:>+10.2f}  '
                  f'{res["total_ds_cruise"]:>+10.2f}  '
                  f'{res["err_avg_pct"]:>+10.6f}  '
                  f'{res["err_cruise_pct"]:>+10.5f}')
            sym_rows.append(dict(
                eta_regen=eta_r, v_low_kmh=vl_kmh,
                s_event_m=ev['s_event'],
                E_event_kWh=ev['E_event'] * _J_TO_KWH,
                ds_avg_m=res['total_ds_avg'],
                ds_cruise_m=res['total_ds_cruise'],
                EP_sim=res['EP_sim'], EP_0=res['EP_0'],
                err_avg_pct=res['err_avg_pct'],
                err_cruise_pct=res['err_cruise_pct'],
            ))
        print()

    # ==================================================================
    # B: Asymmetric events
    # ==================================================================
    print('--- Phase B: Asymmetric Events ---\n')

    asym_cases = [
        (90, 0, 90), (90, 0, 60), (90, 0, 50),
        (90, 30, 90), (90, 30, 60),
        (80, 0, 90), (70, 20, 90),
        (60, 0, 60), (90, 50, 70),
    ]
    asym_rows = []

    for eta_r in [0.0, 0.90]:
        print(f'  [eta_regen = {eta_r:.2f}]')
        hdr = (f'    {"event":>18}  {"s_ev":>7}  {"E_ev":>9}  '
               f'{"ds_ev":>9}  {"ds_tr":>9}  {"ds_tot":>9}  '
               f'{"err_avg":>10}  {"err_crs":>10}')
        print(hdr)
        print('    ' + '-' * (len(hdr) - 4))

        for vi, vl, vo in asym_cases:
            res = compute_delta_s(
                [(vi/3.6, vl/3.6, vo/3.6)], m=m, v_cruise=v_c, d_total=d,
                eta_regen=eta_r)
            ev = res['ev_results'][0]
            label = f'{vi}->{vl}->{vo}'
            print(f'    {label:>18s}  {ev["s_event"]:>7.1f}  '
                  f'{ev["E_event"]*_J_TO_KWH:>9.4f}  '
                  f'{res["sum_ds_events"]:>+9.1f}  '
                  f'{res["sum_ds_trans"]:>+9.1f}  '
                  f'{res["total_ds_avg"]:>+9.1f}  '
                  f'{res["err_avg_pct"]:>+10.6f}  '
                  f'{res["err_cruise_pct"]:>+10.5f}')
            asym_rows.append(dict(
                eta_regen=eta_r, v_entry_kmh=vi, v_low_kmh=vl, v_exit_kmh=vo,
                s_event_m=ev['s_event'],
                E_event_kWh=ev['E_event'] * _J_TO_KWH,
                ds_events_m=res['sum_ds_events'],
                ds_trans_m=res['sum_ds_trans'],
                ds_total_m=res['total_ds_avg'],
                EP_sim=res['EP_sim'], EP_0=res['EP_0'],
                err_avg_pct=res['err_avg_pct'],
                err_cruise_pct=res['err_cruise_pct'],
            ))
        print()

    # ==================================================================
    # C: Mixed-event trip
    # ==================================================================
    print('--- Phase C: Mixed-Event Trip ---\n')

    mixed_events = [
        (v_c, 0.0,     v_c),
        (v_c, 30/3.6,  v_c),
        (v_c, 50/3.6,  v_c),
        (v_c, 0.0,     v_c),
        (v_c, 70/3.6,  v_c),
        (v_c, 10/3.6,  v_c),
    ]
    mixed_labels = [
        'Full stop (traffic light)',
        'Roundabout (90->30->90)',
        'Mild slowdown (90->50->90)',
        'Full stop (junction)',
        'Slight braking (90->70->90)',
        'Near-stop (90->10->90)',
    ]

    mixed_rows = []
    for eta_r in [0.0, 0.42, 0.90]:
        print(f'  [eta_regen = {eta_r:.2f}]')
        res = compute_delta_s(
            mixed_events, m=m, v_cruise=v_c, d_total=d, eta_regen=eta_r)

        print(f'    EP_sim = {res["EP_sim"]:.6f},  EP_0 = {res["EP_0"]:.6f}')
        print(f'    Total ds (avg-ref) = {res["total_ds_avg"]:+.1f} m, '
              f'err = {res["err_avg_pct"]:+.6f}%')
        print(f'    Total ds (crs-ref) = {res["total_ds_cruise"]:+.1f} m, '
              f'err = {res["err_cruise_pct"]:+.5f}%')
        print()
        for i, (ev, label) in enumerate(zip(res['ev_results'], mixed_labels)):
            print(f'      [{i+1}] {label:35s}  '
                  f's={ev["s_event"]:7.1f} m  '
                  f'E={ev["E_event"]*_J_TO_KWH:+8.4f} kWh  '
                  f'ds={ev["delta_s"]:+8.1f} m')
            mixed_rows.append(dict(
                eta_regen=eta_r, event_idx=i+1, event_label=label,
                s_event_m=ev['s_event'],
                E_event_kWh=ev['E_event'] * _J_TO_KWH,
                delta_s_m=ev['delta_s'],
            ))
        print()

    # ==================================================================
    # D: Regen efficiency sweep
    # ==================================================================
    print('--- Phase D: Regen Efficiency Sweep ---\n')

    eta_vals = np.arange(0.0, 1.01, 0.05)
    events_5 = [(v_c, 0.0, v_c)] * 5
    regen_rows = []

    hdr_r = (f'  {"eta_r":>6}  {"EP_sim":>9}  {"EP_0":>9}  '
             f'{"ds_tot":>10}  {"err_avg":>10}  {"err_crs":>10}')
    print(hdr_r)
    print('  ' + '-' * (len(hdr_r) - 2))

    for eta_r in eta_vals:
        res = compute_delta_s(
            events_5, m=m, v_cruise=v_c, d_total=d,
            eta_regen=float(eta_r))
        print(f'  {eta_r:>6.2f}  {res["EP_sim"]:>9.5f}  {res["EP_0"]:>9.5f}  '
              f'{res["total_ds_avg"]:>+10.1f}  '
              f'{res["err_avg_pct"]:>+10.6f}  '
              f'{res["err_cruise_pct"]:>+10.5f}')
        regen_rows.append(dict(
            eta_regen=float(eta_r),
            EP_sim=res['EP_sim'], EP_0=res['EP_0'],
            ds_avg_m=res['total_ds_avg'],
            ds_cruise_m=res['total_ds_cruise'],
            err_avg_pct=res['err_avg_pct'],
            err_cruise_pct=res['err_cruise_pct'],
        ))

    # ==================================================================
    # E: Backward compatibility
    # ==================================================================
    print('\n--- Phase E: Backward Compatibility ---\n')

    n_stops = [0, 1, 2, 5, 10, 15, 20, 25, 30]
    compat_rows = []

    ep0_old = compute_ep(m=m, n_stop=0, eta_regen=0.0)['EP']
    trip0 = simulate_trip([], m=m, eta_regen=0.0)
    print(f'  EP_0 (old model) = {ep0_old:.10f}')
    print(f'  EP_0 (new sim)   = {trip0["EP"]:.10f}')
    print(f'  Match: {abs(ep0_old - trip0["EP"]) < 1e-10}')
    print()

    hdr_e = (f'  {"n":>3}  {"EP_old":>11}  {"EP_new":>11}  '
             f'{"ok":>4}  {"ds_sum":>10}  {"EP_corr":>11}  {"err%":>10}')
    print(hdr_e)
    print('  ' + '-' * (len(hdr_e) - 2))

    for n in n_stops:
        ep_old_n = compute_ep(m=m, n_stop=n, eta_regen=0.0)
        evts = [(v_c, 0.0, v_c)] * n
        trip_n = simulate_trip(evts, m=m, eta_regen=0.0)
        ok = abs(ep_old_n['EP'] - trip_n['EP']) < 1e-6

        if n > 0:
            res_n = compute_delta_s(evts, m=m, eta_regen=0.0)
            ds_s  = res_n['total_ds_avg']
            ep_c  = res_n['EP_corr_avg']
            er    = res_n['err_avg_pct']
        else:
            ds_s, ep_c, er = 0.0, trip_n['EP'], 0.0

        print(f'  {n:>3d}  {ep_old_n["EP"]:>11.7f}  {trip_n["EP"]:>11.7f}  '
              f'{"OK" if ok else "!":>4}  {ds_s:>+10.1f}  '
              f'{ep_c:>11.7f}  {er:>+10.6f}')
        compat_rows.append(dict(
            n_stop=n, EP_old=ep_old_n['EP'], EP_new=trip_n['EP'],
            match=ok, sum_ds_m=ds_s, EP_corrected=ep_c, err_pct=er))

    # ==================================================================
    # F: Numerical example (42 t, 90->30->90, eta_regen=0.90)
    # ==================================================================
    print('\n--- Phase F: Numerical Example (42 t, 90->30->90) ---\n')

    for eta_r in [0.0, 0.90]:
        print(f'  eta_regen = {eta_r}')
        ev = compute_event_energy(v_c, 30/3.6, v_c, m,
                                  eta_regen=eta_r)
        e_c = cruise_energy_rate(v_c, m)
        e_r = simulate_trip([], m=m, eta_regen=eta_r)['E_mech_J'] / d

        dE = ev['E_event'] - e_c * ev['s_event']
        ds = dE / e_r

        print(f'    s_dec      = {ev["s_dec"]:.2f} m')
        print(f'    s_acc      = {ev["s_acc"]:.2f} m')
        print(f'    s_event    = {ev["s_event"]:.2f} m')
        print(f'    E_acc      = {ev["E_acc"]*_J_TO_KWH:.4f} kWh')
        print(f'    E_regen    = {ev["E_regen"]*_J_TO_KWH:.4f} kWh')
        print(f'    E_event    = {ev["E_event"]*_J_TO_KWH:.4f} kWh')
        print(f'    e_cruise   = {e_c:.2f} J/m')
        print(f'    e_ref      = {e_r:.2f} J/m')
        print(f'    dE_i       = {dE:.2f} J = {dE*_J_TO_KWH:.6f} kWh')
        print(f'    Delta_s    = {ds:.2f} m ({ds/1000:.4f} km)')
        print()

    # ==================================================================
    # Save CSV
    # ==================================================================
    RESULTS_TABLE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_TABLE, 'w', encoding='utf-8', newline='') as f:
        f.write('# Exp 9 -- Generalised Distance Correction\n')
        f.write(f'# Baseline: m={m:.0f} kg, v_c={v_c:.1f} m/s\n#\n')

        f.write('# Table 1: Symmetric event sweep\n')
        pd.DataFrame(sym_rows).to_csv(f, index=False)
        f.write('\n# Table 2: Asymmetric events\n')
        pd.DataFrame(asym_rows).to_csv(f, index=False)
        f.write('\n# Table 3: Mixed trip per-event\n')
        pd.DataFrame(mixed_rows).to_csv(f, index=False)
        f.write('\n# Table 4: Regen efficiency sweep\n')
        pd.DataFrame(regen_rows).to_csv(f, index=False)
        f.write('\n# Table 5: Backward compatibility\n')
        pd.DataFrame(compat_rows).to_csv(f, index=False)
    print(f'\n  Saved: {RESULTS_TABLE.name}')

    # ==================================================================
    # Figures
    # ==================================================================
    _plot_symmetric(sym_rows)
    _plot_asymmetric(asym_rows)
    _plot_mixed(mixed_rows, mixed_labels)
    _plot_regen(regen_rows)

    return dict(
        symmetric=sym_rows, asymmetric=asym_rows,
        mixed=mixed_rows, regen=regen_rows, compat=compat_rows,
    )


# ======================================================================
# 5. Plots
# ======================================================================

def _plot_symmetric(rows):
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W * 1.2, FIG_H), dpi=DPI)

    for ax, eta_r, label in zip(
        axes, [0.0, 0.90],
        [r'$\eta_{regen} = 0$', r'$\eta_{regen} = 0.90$']
    ):
        sub = [r for r in rows if r['eta_regen'] == eta_r]
        vl  = [r['v_low_kmh'] for r in sub]
        ds  = [r['ds_avg_m'] for r in sub]
        dsc = [r['ds_cruise_m'] for r in sub]
        ep  = [r['EP_sim'] for r in sub]
        ep0 = sub[0]['EP_0']

        ax2 = ax.twinx()
        l1, = ax.plot(vl, ds, 'D-', color='#2196F3', ms=7, lw=FIT_LW,
                      label=r'$\Delta s$ (trip-avg ref)', zorder=5)
        l2, = ax.plot(vl, dsc, '^--', color='#FF9800', ms=6, lw=1.5,
                      label=r'$\Delta s$ (cruise ref)', alpha=0.8, zorder=4)
        l3, = ax2.plot(vl, ep, 'o-', color='#E91E63', ms=6, lw=FIT_LW,
                       label=r'$EP_{sim}$', zorder=5)
        ax2.axhline(ep0, color='grey', ls=':', lw=1, alpha=0.7)

        ax.set_xlabel(r'$v_{low}$ (km/h)', fontsize=FS_LABEL)
        ax.set_ylabel(r'$\Delta s$ per event (m)', fontsize=FS_LABEL)
        ax2.set_ylabel('EP (kWh/km)', fontsize=FS_LABEL)
        ax.set_title(f'Symmetric events, {label}', fontsize=FS_TITLE)
        ax.legend([l1, l2, l3], [l.get_label() for l in [l1, l2, l3]],
                  fontsize=FS_LEGEND, loc='upper right')

    fig.suptitle(
        r'Exp 9(a) -- $\Delta s$ vs $v_{low}$ for Symmetric Events '
        r'($v_c \to v_{low} \to v_c$, $m = 42$ t)',
        fontsize=FS_TITLE + 1, y=1.02)
    fig.tight_layout()
    RESULTS_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(RESULTS_FIG, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {RESULTS_FIG.name}')


def _plot_asymmetric(rows):
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W * 1.2, FIG_H * 1.1), dpi=DPI)

    for ax, eta_r, ttl in zip(
        axes, [0.0, 0.90],
        [r'$\eta_{regen} = 0$', r'$\eta_{regen} = 0.90$']
    ):
        sub = [r for r in rows if r['eta_regen'] == eta_r]
        labels = [f'{r["v_entry_kmh"]}->{r["v_low_kmh"]}->{r["v_exit_kmh"]}'
                  for r in sub]
        ds_ev = [r['ds_events_m'] for r in sub]
        ds_tr = [r['ds_trans_m'] for r in sub]

        y = np.arange(len(labels))
        bars_ev = ax.barh(y, ds_ev, height=0.5, color='#42A5F5', alpha=0.85,
                          edgecolor='#333', label='Event')
        bars_tr = ax.barh(y, ds_tr, left=ds_ev, height=0.5,
                          color='#FF7043', alpha=0.85,
                          edgecolor='#333', label='Transition')
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel(r'$\Delta s$ (m)', fontsize=FS_LABEL)
        ax.set_title(f'Asymmetric events, {ttl}', fontsize=FS_TITLE)
        ax.axvline(0, color='grey', lw=0.8)
        ax.legend(fontsize=FS_LEGEND, loc='best')

        for bar, val in zip(bars_ev, [r['ds_total_m'] for r in sub]):
            x_total = val
            ax.text(x_total + (50 if x_total >= 0 else -50),
                    bar.get_y() + bar.get_height()/2,
                    f'{val:+.0f}', ha='left' if x_total >= 0 else 'right',
                    va='center', fontsize=8)

    fig.suptitle(
        r'Exp 9(b) -- $\Delta s$ for Asymmetric Events ($m = 42$ t)',
        fontsize=FS_TITLE + 1, y=1.02)
    fig.tight_layout()
    fig.savefig(RESULTS_FIG2, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {RESULTS_FIG2.name}')


def _plot_mixed(rows, labels):
    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H * 1.1), dpi=DPI)

    eta_vals = sorted(set(r['eta_regen'] for r in rows))
    n_ev = len(labels)
    bw = 0.25
    x_base = np.arange(n_ev)
    colours = ['#E91E63', '#2196F3', '#4CAF50']

    for j, eta_r in enumerate(eta_vals):
        sub = [r for r in rows if r['eta_regen'] == eta_r]
        ds  = [r['delta_s_m'] for r in sub]
        ax.bar(x_base + j * bw, ds, width=bw, color=colours[j],
               alpha=0.85, edgecolor='#333',
               label=fr'$\eta_{{regen}} = {eta_r:.2f}$')

    ax.set_xticks(x_base + bw)
    short = ['Full stop\n(light)', 'Roundabout\n(90->30)',
             'Mild slow\n(90->50)', 'Full stop\n(junction)',
             'Slight brake\n(90->70)', 'Near-stop\n(90->10)']
    ax.set_xticklabels(short, fontsize=9)
    ax.set_ylabel(r'$\Delta s_i$ per event (m)', fontsize=FS_LABEL)
    ax.set_title(
        r'Exp 9(c) -- Per-Event $\Delta s$ in a Mixed Trip ($m = 42$ t)',
        fontsize=FS_TITLE)
    ax.axhline(0, color='grey', lw=0.8)
    ax.legend(fontsize=FS_LEGEND, loc='best')

    fig.tight_layout()
    fig.savefig(RESULTS_FIG3, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {RESULTS_FIG3.name}')


def _plot_regen(rows):
    apply_style()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FIG_W * 1.2, FIG_H), dpi=DPI)

    et  = [r['eta_regen'] for r in rows]
    dsa = [r['ds_avg_m'] for r in rows]
    dsc = [r['ds_cruise_m'] for r in rows]
    ea  = [r['err_avg_pct'] for r in rows]
    ec  = [r['err_cruise_pct'] for r in rows]

    ax1.plot(et, dsa, 'D-', color='#2196F3', ms=5, lw=FIT_LW,
             label=r'$\Sigma\Delta s$ (trip-avg)')
    ax1.plot(et, dsc, '^--', color='#FF9800', ms=5, lw=1.5,
             label=r'$\Sigma\Delta s$ (cruise)', alpha=0.8)
    ax1.set_xlabel(r'$\eta_{regen}$', fontsize=FS_LABEL)
    ax1.set_ylabel(r'$\Sigma\Delta s$ for 5 stops (m)', fontsize=FS_LABEL)
    ax1.set_title(r'(a) Total $\Delta s$ vs $\eta_{regen}$', fontsize=FS_TITLE)
    ax1.legend(fontsize=FS_LEGEND)
    ax1.axhline(0, color='grey', lw=0.8, ls=':')

    ax2.plot(et, ea, 'D-', color='#4CAF50', ms=5, lw=FIT_LW,
             label='Trip-avg ref')
    ax2.plot(et, ec, '^--', color='#F44336', ms=5, lw=1.5,
             label='Cruise ref', alpha=0.8)
    ax2.set_xlabel(r'$\eta_{regen}$', fontsize=FS_LABEL)
    ax2.set_ylabel('Correction error (%)', fontsize=FS_LABEL)
    ax2.set_title(r'(b) Error vs $\eta_{regen}$', fontsize=FS_TITLE)
    ax2.legend(fontsize=FS_LEGEND)
    ax2.axhline(0, color='grey', lw=0.8, ls=':')

    fig.suptitle(
        r'Exp 9(d) -- Regen Efficiency Sweep (5 full stops, $m = 42$ t)',
        fontsize=FS_TITLE + 1, y=1.02)
    fig.tight_layout()
    fig.savefig(RESULTS_FIG4, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {RESULTS_FIG4.name}')


if __name__ == '__main__':
    run()
