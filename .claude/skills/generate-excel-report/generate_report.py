
'''
示例1: python generate_report.py -veh KY24LHT -ds 2025-10-01 -de 2025-10-31
示例2: python generate_report.py -veh YK73WFN -ds 2025-08-25 -de 2025-08-25
示例3: python generate_report.py -veh KY24LHT -ds 2025-10-01 -de 2025-10-31 --debug
示例4: python generate_report.py -veh KY24LHT -ds 2025-10-01 -de 2025-10-31 --fast
示例5: python generate_report.py -veh KY24LHT -ds 2025-10-01 -de 2025-10-31 --out-dir ./excel_report_database/2.2.4
示例6: python generate_report.py -veh KY24LHT -ds 2025-10-01 -de 2025-10-31 --raw-only  # 存 raw+HTML、不画烤版图（提速）
'''
import argparse
import logging
from jolt_toolkit import __version__
from jolt_toolkit.report_generator._generator import JOLTReportGenerator
from dotenv import load_dotenv

def main() -> int:
    parser = argparse.ArgumentParser(description='Generate JOLT Excel report.')
    parser.add_argument('-veh',
                        '--vehicle_registration',
                        type=str,
                        help='The vehicle registration')
    parser.add_argument('-ds',
                        '--date_start',
                        type=str,
                        help='The start date')
    parser.add_argument('-de',
                        '--date_end',
                        type=str,
                        help='The end date')
    parser.add_argument('--debug',
                        action='store_true',
                        default=False,
                        help='Enable debug mode: generate validation figures and save raw telematics CSV')
    parser.add_argument('--raw-only',
                        dest='raw_only',
                        action='store_true',
                        default=False,
                        help=('Save raw telematics CSV + inspect HTML (like --debug), but skip '
                              'drawing the baked validation figures during generation. Use this '
                              'when figures will be re-drawn afterwards via the overlay '
                              'regenerate step, to avoid plotting them twice.'))
    parser.add_argument('--fast',
                        action='store_true',
                        default=False,
                        help='Fast mode: skip SRF Logger and Charger data fetching')
    parser.add_argument('--out-dir',
                        '--report-output-folder',
                        dest='out_dir',
                        type=str,
                        default=None,
                        help=('Output folder for the report. Defaults to '
                              './excel_report_database/<package_version>. The version '
                              'comes from the installed jolt_toolkit, which is shared '
                              'across the conda env, so confirm it before a batch run.'))
    args = parser.parse_args()

    load_dotenv('.env')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    logging.info("JOLT Report Generator v%s", __version__)

    # 输出目录默认由已安装的 jolt_toolkit 版本号决定；可用 --out-dir 显式覆盖。
    out_dir = args.out_dir or f"./excel_report_database/{__version__}"
    logging.info("Report output folder: %s", out_dir)

    # --raw-only：仍落盘 raw CSV + inspect HTML（需 debug_mode 落盘），但跳过烤版图。
    debug_mode = args.debug or args.raw_only
    save_figures = not args.raw_only

    jolt_excel_report_generator = JOLTReportGenerator(
        report_output_folder=out_dir,
        overwrite_existing_report=True,
        debug_mode=debug_mode,
        fast_mode=args.fast,
        save_figures=save_figures,
    )
    jolt_excel_report_generator.generate_report(
        vehicle_registration=args.vehicle_registration,
        date_start=args.date_start,
        date_end=args.date_end,
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
