"""Import contract for the v3.0.0 architecture.

The v3.0.0 refactor split the two monoliths (``segment_algorithms.py`` and
``report_builder.py``) into sub-packages while keeping the original module paths
as facades. This test locks in the §0.2 compatibility surface: every core module
and facade must import, every historically-importable public/private name must
still resolve on its ORIGINAL import path, and the single shared ``VEHICLE_CONFIG``
object must be identical across the modules that load / re-export it.

No network / no SRF key: importing a module never issues an API request (the SRF
client is only built inside ``JOLTReportGenerator.__init__``), so this is offline.
"""

import importlib

import pytest

# ── Core modules + facades that must import cleanly ──────────────────────────
CORE_MODULES = [
    "jolt_toolkit",
    "jolt_toolkit.configs",
    "jolt_toolkit.analysis",
    "jolt_toolkit.analysis.counters",
    "jolt_toolkit.analysis.physics",
    "jolt_toolkit.analysis.stats",
    "jolt_toolkit.report_generator",
    "jolt_toolkit.report_generator._generator",
    "jolt_toolkit.report_generator.capacity",
    "jolt_toolkit.report_generator.capacity_backfill",
    "jolt_toolkit.report_generator.charger_patcher",
    "jolt_toolkit.report_generator.logger_patcher",
    "jolt_toolkit.report_generator.weather_patcher",
    "jolt_toolkit.report_generator.weather_patch",
    "jolt_toolkit.report_generator.diesel_pipeline",
    "jolt_toolkit.report_generator.data_fetcher",
    "jolt_toolkit.report_generator.data_class",
    "jolt_toolkit.report_generator.operators",
    "jolt_toolkit.report_generator.pedal_histogram",
    "jolt_toolkit.report_generator.paths",
    "jolt_toolkit.report_generator.cli",
    "jolt_toolkit.report_generator.xlsx_patch_common",
    # report_builder split + facade
    "jolt_toolkit.report_generator.report_builder",
    "jolt_toolkit.report_generator.columns",
    "jolt_toolkit.report_generator.charts",
    "jolt_toolkit.report_generator.row_builder",
    "jolt_toolkit.report_generator.excel_writer",
    "jolt_toolkit.report_generator.html_viewer",
    # segmentation split + facade
    "jolt_toolkit.report_generator.segment_algorithms",
    "jolt_toolkit.report_generator.segmentation",
    "jolt_toolkit.report_generator.segmentation.constants",
    "jolt_toolkit.report_generator.segmentation.timeutil",
    "jolt_toolkit.report_generator.segmentation.mass_aggregation",
    "jolt_toolkit.report_generator.segmentation.soc_detection",
    "jolt_toolkit.report_generator.segmentation.speed_detection",
    "jolt_toolkit.report_generator.segmentation.mass_clustering",
    "jolt_toolkit.report_generator.segmentation.validation_figure",
    "jolt_toolkit.report_generator.segmentation.detection",
    # weather infra
    "jolt_toolkit.report_generator.weather_fetcher",
    "jolt_toolkit.report_generator.weather_fetcher.openweather",
    "jolt_toolkit.report_generator.weather_fetcher.fine_grained_patcher",
    # SRF-free migration scripts
    "jolt_toolkit.scripts.recompute_from_cache",
    "jolt_toolkit.scripts.refresh_inspect_html",
]

# ── §0.2 compatibility surface: name -> original import module ───────────────
# These names are imported by external consumers (skills, finetune, dashboards,
# recompute, patchers). They must keep resolving on the facade module path.
SEGMENT_ALGORITHMS_NAMES = [
    "run_segment_detection",
    "resolve_mass_agg",
    "cluster_mass_data",
    "find_speed_trips",
    "find_discharge_segments_by_speed",
    "find_charge_segments_by_soc",
    "find_discharge_segments_by_soc",
    "merge_discharge_by_mass",
    "split_discharge_by_mass",
    "plot_leg_validation",
    "_agg_mass",
    "_ANCHOR_PRIVATE_KEYS",
    "_TEXT_BBOX",
    "_export_overlay_boxes",
    "_recompute_anchors",
    "_enforce_anchor_ordering",
    "_detect_cluster_transitions",
    "_to_utc",
    "_HAS_MPL",
    "VEHICLE_CONFIG",
    "PIPELINE_CONFIGS",
    # column-name constants (the *_COL surface)
    "TIME_COL",
    "SOC_COL",
    "MASS_COL",
    "MOVING_COL",
    "RECUP_COL",
    "AC_COL",
    "DC_COL",
    "TOTAL_ENERGY_COL",
    "MOVING_SPEED_THRESHOLD_KMH",
]

REPORT_BUILDER_NAMES = [
    "HEADERS",
    "DIESEL_HEADERS",
    "is_trip_leg",
    "_row_col_index",
    "_is_nan",
    "_leg_is_charge",
    "_leg_is_stop",
    "_seg_to_row",
    "_insert_stop_rows",
    "_stop_row_from_neighbours",
    "_write_excel_report",
    "_write_html_viewer",
    "_write_na",
    "_find_overlap",
    "_build_logger_url",
    "_build_telematics_url",
    "_build_charger_url",
    "_kinetics_corrected_energy_perf",
    "_get_trip_speed_array",
    "_get_postcode",
    "CHART_SPECS_EV",
    "CHART_SPECS_DIESEL",
    "chart_specs_for",
    # telematics col-name constants re-exported from columns
    "_WEIGHT_COL",
    "_SPEED_COL",
    "_RECUP_COL",
    "_PROPULSION_COL",
]

# capacity names re-exported for capacity_backfill / recompute back-compat
CAPACITY_NAMES = [
    "_correct_effective_capacity",
    "_persist_effective_capacity",
    "_period_capacity_from_rows",
    "_recompute_weighted_capacity",
    "_cap_is_valid",
    "_soc_weighted_cap",
    "_IDX_CAP",
    "MIN_DONORS",
    "CAP_WINDOW_HALF_DAYS",
]


@pytest.mark.parametrize("modname", CORE_MODULES)
def test_module_imports(modname):
    assert importlib.import_module(modname) is not None


@pytest.mark.parametrize("name", SEGMENT_ALGORITHMS_NAMES)
def test_segment_algorithms_facade_name(name):
    mod = importlib.import_module("jolt_toolkit.report_generator.segment_algorithms")
    assert hasattr(mod, name), f"segment_algorithms.{name} no longer resolves"


@pytest.mark.parametrize("name", REPORT_BUILDER_NAMES)
def test_report_builder_facade_name(name):
    mod = importlib.import_module("jolt_toolkit.report_generator.report_builder")
    assert hasattr(mod, name), f"report_builder.{name} no longer resolves"


@pytest.mark.parametrize("name", CAPACITY_NAMES)
def test_capacity_backcompat_name(name):
    # Importable both from capacity (new home) and _generator (re-export).
    cap = importlib.import_module("jolt_toolkit.report_generator.capacity")
    gen = importlib.import_module("jolt_toolkit.report_generator._generator")
    assert hasattr(cap, name), f"capacity.{name} missing"
    assert hasattr(gen, name), f"_generator re-export of {name} missing"


def test_correct_effective_capacity_staticmethod_identity():
    """recompute_from_cache calls JOLTReportGenerator._correct_effective_capacity;
    it must be the same object as the capacity module function."""
    cap = importlib.import_module("jolt_toolkit.report_generator.capacity")
    gen = importlib.import_module("jolt_toolkit.report_generator._generator")
    assert (
        gen.JOLTReportGenerator._correct_effective_capacity
        is cap._correct_effective_capacity
    )
    assert (
        gen.JOLTReportGenerator._persist_effective_capacity
        is cap._persist_effective_capacity
    )


def test_vehicle_config_object_identity():
    """VEHICLE_CONFIG / PIPELINE_CONFIGS are loaded once and shared by reference
    across the facade, the segmentation constants module, and report_builder."""
    sa = importlib.import_module("jolt_toolkit.report_generator.segment_algorithms")
    rb = importlib.import_module("jolt_toolkit.report_generator.report_builder")
    sc = importlib.import_module("jolt_toolkit.report_generator.segmentation.constants")
    assert sa.VEHICLE_CONFIG is sc.VEHICLE_CONFIG
    assert sa.VEHICLE_CONFIG is rb.VEHICLE_CONFIG
    assert sa.PIPELINE_CONFIGS is sc.PIPELINE_CONFIGS


def test_import_sets_matplotlib_agg_backend():
    """Importing the segmentation/report path must select the headless Agg
    backend (validation_figure runs matplotlib.use('Agg') at import)."""
    importlib.import_module("jolt_toolkit.report_generator.segment_algorithms")
    import matplotlib

    assert matplotlib.get_backend().lower() == "agg"
