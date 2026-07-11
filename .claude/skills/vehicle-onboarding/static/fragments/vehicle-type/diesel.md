# Vehicle type: diesel — SRF-Logger J1939 path (no speed/SOC branch)

Loads at Phase 2 §2.1 when SRF `fuel` = DIESEL. Section numbers (§2.4) refer to the core
workflow, `static/core/workflow.md`; `references/` paths are relative to the skill root.

> **DIESEL vehicles (SRF `fuel` = DIESEL) skip the EV speed/SOC branch entirely.**
> They have **no battery/SOC**; their data is **SRF Logger** (`leg.trip.source` starts
> with `SRFLOGGER`, channel set via `leg_source: SRFLOGGER_V1`), not FPS telematics
> (a diesel's FPS leg is usually IMU-only — speed/fuel live in the Logger J1939
> channels). Configure them like the existing diesel vehicle **WU70GLV** (template):
> `fuel_type: DIESEL`, `pipeline: daf_diesel_logger` (a routing label — the channel
> names live in `vehicles.json`, so the same pipeline serves any OEM whose Logger
> exposes the standard J1939 channels), `leg_source: SRFLOGGER_V1`, plus the channel
> mappings `speed_col`=`CCVS wheel based vehicle speed`, `fuel_energy_col`=`LFC engine
> total fuel used`, `fuel_rate_col`=`LFE fuel rate`, `distance_col`=`VDHR hr total
> vehicle distance`, `mass_col`=`CVW gross combination vehicle weight`,
> `altitude_col`=`2 altitude`, `ambient_temp_col`=`AMB ambient air temperature`,
> `speed_col_fallback`=`2 speed`, and `diesel_lhv_kwh_per_l: 10.0`. **Discover a new
> diesel's channels** by listing `leg.types` and `leg.get_data_frame(<channel>)`
> columns on a `SRFLOGGER` leg (channels CCVS/LFC/LFE/VDHR/CVW/AMB/2/7); these J1939
> names are OEM-independent, so a new diesel usually reuses `daf_diesel_logger`
> verbatim. See `references/YT21EFD.md` (Scania) + `references/WU70GLV` for worked
> examples. Then jump to §2.4 (no speed/SOC branch question for diesel).
