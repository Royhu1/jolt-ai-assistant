"""
Excel report writer.

Keep this module dumb: it should only accept already-prepared rows/tables and
write them to disk. All business logic belongs in fetch/process/standard Excel output steps.
"""

from __future__ import annotations
import re
import logging
import datetime
import numbers
import dataclasses
from pathlib import Path
from typing import Any
import os
import pandas as pd
import xlsxwriter

from jolt_toolkit.report_generator.data_class import LegRecord, Link
_LOG = logging.getLogger("jolt")

class ExcelWriter():
    def __init__(self,
                 output_folder: str,
                 overwrite_existing_report: bool,
                 debug_mode: bool,
                 version: str):

        self.output_folder = output_folder
        self.overwrite_existing_report = overwrite_existing_report
        self.debug_mode = debug_mode
        self.version = version

    def write_excel_report(self,
                           leg_record_list: list[LegRecord],
                           vehicle_registration: str,
                           date_start: datetime.datetime,
                           date_end: datetime.datetime) -> Path:

        
        # 确保输出文件夹存在
        os.makedirs(self.output_folder, exist_ok=True)
        # 定义输出文件名
        output_file_name = self._make_output_file_name(vehicle_registration, date_start, date_end)
        # 确定输出文件路径
        output_path = os.path.join(self.output_folder, output_file_name)
        if os.path.exists(output_path) and not self.overwrite_existing_report:
            raise FileExistsError(f"Report already exists: {output_path}")
        
        # 创建Excel工作簿和工作表
        workbook = xlsxwriter.Workbook(
            output_path, {"nan_inf_to_errors": True, "remove_timezone": True}
        )
        data_worksheet = workbook.add_worksheet("Data")
        graphs_worksheet = workbook.add_worksheet("Graphs")
        definitions_worksheet = workbook.add_worksheet("Definitions")

        # 写入数据工作表
        # 1) 写表头
        # 生成表头
        leg_fields = dataclasses.fields(LegRecord)
        headers = [field.name for field in leg_fields]
        header_lookup = {
            field.name: field.metadata.get("Excel Header", field.name)
            for field in leg_fields
        }
        header_labels = [header_lookup[name] for name in headers]
        decimal_places_map = {
            field.name: field.metadata.get("decimal_places")
            for field in leg_fields
            if field.metadata.get("decimal_places") is not None
        }
        header_format = workbook.add_format({"align": "center", "valign": "vcenter", "bold": True})
        max_col_widths = [len(str(h)) for h in header_labels]
        for col_idx, header in enumerate(header_labels):
            data_worksheet.write(0, col_idx, header, header_format)

        # 2) 写数据
        # 定义单元格格式
        datasheet_formats = {
            'red': {
                pd.Timestamp: workbook.add_format({
                    'align': 'center', 'bg_color': '#FFC7CE',
                    'num_format': 'yyyy-mm-dd hh:mm:ss'
                }),
                pd.Timedelta: workbook.add_format({
                    'align': 'center', 'bg_color': '#FFC7CE',
                    'num_format': '[hh]:mm:ss'
                }),
                pd.Timedelta: workbook.add_format({
                    'align': 'center', 'bg_color': '#FFC7CE',
                    'num_format': '[hh]:mm:ss'
                }),
                pd.Timedelta: workbook.add_format({
                    'align': 'center', 'bg_color': '#FFC7CE',
                    'num_format': '[hh]:mm:ss'
                }),
                Link: workbook.add_format({
                    'align': 'center', 'bg_color': '#FFC7CE',
                    'font_color': '#0000FF', 'underline': True
                }),
                '_': workbook.add_format({
                    'align': 'center', 'bg_color': '#FFC7CE'
                })
            },
            'green': {
                pd.Timestamp: workbook.add_format({
                    'align': 'center', 'bg_color': '#C6EFCE',
                    'num_format': 'yyyy-mm-dd hh:mm:ss'
                }),
                pd.Timedelta: workbook.add_format({
                    'align': 'center', 'bg_color': '#C6EFCE',
                    'num_format': '[hh]:mm:ss'
                }),
                pd.Timedelta: workbook.add_format({
                    'align': 'center', 'bg_color': '#C6EFCE',
                    'num_format': '[hh]:mm:ss'
                }),
                Link: workbook.add_format({
                    'align': 'center', 'bg_color': '#C6EFCE',
                    'font_color': '#0000FF', 'underline': True
                }),
                '_': workbook.add_format({
                    'align': 'center', 'bg_color': '#C6EFCE'
                })
            }
        }

        # 写入数据行
        number_format_cache: dict[tuple[str, int], xlsxwriter.format.Format] = {}

        def get_number_format(theme: str, decimals: int) -> xlsxwriter.format.Format:
            key = (theme, decimals)
            fmt = number_format_cache.get(key)
            if fmt is not None:
                return fmt
            bg_color = "#FFC7CE" if theme == "red" else "#C6EFCE"
            num_format = "0" if decimals <= 0 else ("0." + ("0" * decimals))
            fmt = workbook.add_format(
                {"align": "center", "valign": "vcenter", "bg_color": bg_color, "num_format": num_format}
            )
            number_format_cache[key] = fmt
            return fmt

        for row_idx, leg_record in enumerate(leg_record_list, start=1):
            row_dict = {name: getattr(leg_record, name) for name in headers}  # 列名->值（列名需是合法标识符；如果不是，见下方“稳健版”）

            # 行级颜色：默认绿，充电红
            leg_type = row_dict.get("leg_type", None)
            row_theme = "green"
            row_fmt = datasheet_formats[row_theme]
            if isinstance(leg_type, str) and re.search(r"\bCharge\b", leg_type, re.IGNORECASE):
                row_theme = "red"
                row_fmt = datasheet_formats[row_theme]

            # 逐列写入
            for col_idx, col_name in enumerate(headers):
                value = row_dict.get(col_name, pd.NA)
                display_text = value

                # ---- Timedelta: 转成 Excel 需要的“天数小数” ----
                if isinstance(value, pd.Timedelta) and not pd.isna(value):
                    cell_fmt = row_fmt.get(pd.Timedelta, row_fmt["_"])
                    value = value.total_seconds() / 86400.0
                    display_text = "00:00:00"
                elif isinstance(value, pd.Timedelta) and not pd.isna(value):
                    cell_fmt = row_fmt.get(pd.Timedelta, row_fmt["_"])
                    value = value.total_seconds() / 86400.0
                    display_text = "00:00:00"
                elif pd.isna(value):
                    cell_fmt = row_fmt["_"]
                    value = "=NA()"
                    display_text = "NA"
                else:
                    cell_fmt = row_fmt.get(type(value), row_fmt["_"])

                decimals = decimal_places_map.get(col_name)
                if (
                    decimals is not None
                    and isinstance(value, numbers.Real)
                    and not isinstance(value, bool)
                    and not pd.isna(value)
                ):
                    decimals = int(decimals)
                    value = round(float(value), decimals)
                    cell_fmt = get_number_format(row_theme, decimals)
                    display_text = f"{value:.{decimals}f}"

                # ---- Link: 写超链接 ----
                if isinstance(value, Link):
                    data_worksheet.write_url(
                        row_idx, col_idx, value.href,
                        string=value.text, cell_format=cell_fmt
                    )
                    display_text = value.text
                else:
                    if isinstance(value, (tuple, list)):
                        value = ", ".join(map(str, value))
                        display_text = value
                    elif isinstance(value, pd.Timestamp) and getattr(value, "tzinfo", None) is not None:
                        display_text = value.tz_localize(None).strftime("%Y-%m-%d %H:%M:%S")
                    data_worksheet.write(row_idx, col_idx, value, cell_fmt)

                try:
                    width = len(str(display_text))
                except Exception:
                    width = 0
                if width > max_col_widths[col_idx]:
                    max_col_widths[col_idx] = width

        for col_idx, max_len in enumerate(max_col_widths):
            data_worksheet.set_column(col_idx, col_idx, min(max(max_len + 2, 12), 255))

        data_worksheet.freeze_panes(1, 0)

        col_key_to_idx = {name: idx for idx, name in enumerate(headers)}
        last_row = len(leg_record_list)
        if last_row:
            graphs: list[tuple[str, str]] = [
                ("vehicle_weight", "energy_performance"),
                ("avg_temp", "energy_performance"),
                ("cumulative_distance", "cumulative_co2"),
                ("avg_pressure", "energy_performance"),
                ("avg_humidity", "energy_performance"),
                ("avg_wind_speed", "energy_performance"),
                ("charging_rate", "energy_efficiency"),
                ("average_speed", "energy_performance"),
            ]

            def label_for(col_key: str) -> str:
                return header_lookup.get(col_key, col_key)

            chart_idx = 0
            for x_key, y_key in graphs:
                x_col = col_key_to_idx.get(x_key)
                y_col = col_key_to_idx.get(y_key)
                if x_col is None or y_col is None:
                    continue

                x_label = label_for(x_key)
                y_label = label_for(y_key)

                chart = workbook.add_chart({"type": "scatter"})
                chart.add_series(
                    {
                        "name": f"{y_label} vs {x_label}",
                        "categories": ["Data", 1, x_col, last_row, x_col],
                        "values": ["Data", 1, y_col, last_row, y_col],
                        "trendline": {"type": "linear", "display_equation": True, "display_r_squared": True},
                    }
                )

                # Set x-axis with specific settings for vehicle_weight
                if x_key == "vehicle_weight":
                    chart.set_x_axis({
                        "name": x_label,
                        "min": 0,
                        "max": 50000,
                        "major_unit": 5000
                    })
                else:
                    chart.set_x_axis({"name": x_label})

                if y_key == "energy_performance":
                    chart.set_y_axis({"name": y_label, "min": 0, "max": 3})
                else:
                    chart.set_y_axis({"name": y_label})
                chart.set_title({"name": f"{y_label} vs {x_label}"})

                insert_row = chart_idx * 20 + 1
                graphs_worksheet.insert_chart(f"A{insert_row}", chart, {"x_scale": 1.3, "y_scale": 1.3})
                chart_idx += 1

        # TODO: 写入定义工作表

        fmt = workbook.add_format({'text_wrap': True, 'valign': 'top'})

        texts = [
            (
                "SOC: State of Charge. The percentage of the battery capacity " +
                "that is currently charged."
            ),
            (
                "Battery Capacity Default: The nominal battery capacity from vehicle " +
                "configuration. This is the manufacturer-specified or configured value " +
                "for the vehicle, used as the baseline for energy calculations."
            ),
            (
                "Battery Capacity Calibrated: Calculated battery capacity based on " +
                "energy and SOC change. Uses three-tier fallback strategy: " +
                "(1) Priority: Charging data (96 series AC/DC channels) for Volvo, " +
                "(2) Fallback: Discharging data (95 series channels) for Scania, " +
                "(3) Default: Vehicle config nominal value if no calibration data available."
            ),
            (
                "Peak Charging : The highest charging rate during the trip " +
                "based on per minute charger output."
            ),
            (
                "Energy based on torque: Simpson integral of percent torque " +
                "times nominal torque and engine speed."
            ),
            (
                "Energy Performance is currently calculated from energy based " +
                "on motor power divided by distance, or energy from battery "
                "divided by distance if there is no logger data. "
            )
        ]

        for r, t in enumerate(texts):
            definitions_worksheet.write(r, 0, t, fmt)

        # (longest string + padding) × 1.1
        width = (max(map(len, texts)) + 5) * 1.1
        definitions_worksheet.set_column(0, 0, width, fmt)
        # 设置文件属性

        workbook.set_properties({
            'title': f'JOLT Report for {vehicle_registration}',
            'subject': f'From {date_start} to {date_end}',
            'author': 'Centre for Sustainable Road Freight',
            'comments': f"Generated by JOLT v{self.version}",
        })
        workbook.close()
        return Path(output_path)
        
    @staticmethod
    def _make_output_file_name(vehicle_registration: str, date_start: datetime.datetime, date_end: datetime.datetime) -> Path:
        # jolt_report_<vehicle_registration>_<startdate>_<enddate>.xlsx
        vehicle_registration = vehicle_registration
        start_date = date_start.strftime("%Y%m%d")
        end_date = date_end.strftime("%Y%m%d")
        file_name = f"jolt_report_{vehicle_registration}_{start_date}_{end_date}.xlsx"
        return file_name
    


