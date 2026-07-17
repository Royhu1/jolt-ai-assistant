# Canonical home since v3.1.0 (P1 copy, 2026-07-17): moved here from
# src/jolt_toolkit/vehicle_params_identificator/__init__.py — the param-identifier
# agent's workspace (research_projects/parameter_identify/) now owns the
# identification code (the package original is removed in P2). Standalone entry:
#   python research_projects/parameter_identify/code/run_identification.py --help
"""
vehicle_params_identificator — 滚阻 / 风阻参数辨识子包。

公开 API：
  identify_crr_cda()   对指定车辆进行 C_rr, C_dA 参数辨识
"""


def identify_crr_cda(
    vehicle_registration: str,
    date_start: str,
    date_end: str,
) -> None:
    """便捷函数：运行 C_rr / C_dA 参数辨识。"""
    from run_identification import main

    main(registration=vehicle_registration, date_start=date_start, date_end=date_end)
