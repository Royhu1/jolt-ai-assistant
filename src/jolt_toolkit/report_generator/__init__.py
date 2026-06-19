"""
report_generator — 报告生成子包。

公开 API：
  generate_report()   生成单车 Excel 报告
  patch_logger()      Logger 天气数据补全
"""

from jolt_toolkit.report_generator._generator import JOLTReportGenerator


def generate_report(
    vehicle_registration: str,
    date_start: str,
    date_end: str,
    *,
    mode: str = "normal",
    debug: bool = False,
    save_figures: bool = True,
    outputfolder: str = "excel_report_database",
) -> None:
    """便捷函数：生成单车 Excel 报告。

    ``save_figures=False`` 仅在 ``debug=True`` 时有意义：仍落盘 raw CSV + inspect HTML，
    但跳过 generate 阶段烤入标注的 validation 图（对应 CLI 的 ``--raw-only``）。
    """
    from jolt_toolkit import __version__
    gen = JOLTReportGenerator(
        report_output_folder=f"./{outputfolder}/{__version__}",
        overwrite_existing_report=True,
        debug_mode=debug,
        fast_mode=(mode == "fast"),
        save_figures=save_figures,
    )
    gen.generate_report(
        vehicle_registration=vehicle_registration,
        date_start=date_start,
        date_end=date_end,
    )


def patch_logger(
    vehicle_registration: str,
    date_start: str,
    date_end: str,
    *,
    debug: bool = False,
) -> None:
    """便捷函数：Logger 天气数据补全。"""
    from jolt_toolkit.report_generator.logger_patcher import LoggerPatcher
    patcher = LoggerPatcher()
    patcher.patch(vehicle_registration, date_start, date_end, debug=debug)
