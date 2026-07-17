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
    from jolt_toolkit.vehicle_params_identificator.run_identification import main

    main(registration=vehicle_registration, date_start=date_start, date_end=date_end)
