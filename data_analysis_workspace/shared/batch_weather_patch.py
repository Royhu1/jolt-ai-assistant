"""批量运行 WeatherPatcher 补全所有报告的天气数据。"""
import sys
import os
import logging
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s %(levelname)s %(message)s")

# 加载 .env
PROJECT_ROOT = Path(__file__).resolve().parents[2]
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

keys = os.environ.get("OPENWEATHER_API_KEYS", "")
print(f"OpenWeather API Keys: {len(keys.split(','))} 个")

sys.path.insert(0, str(PROJECT_ROOT / "src"))
from jolt_toolkit.report_generator.weather_patcher import WeatherPatcher

patcher = WeatherPatcher()
report_dir = PROJECT_ROOT / "excel_report_database" / "2.0.0.dev0"

total_patched = 0
for veh_dir in sorted(report_dir.iterdir()):
    if not veh_dir.is_dir():
        continue
    print(f"\n=== {veh_dir.name} ===")
    try:
        results = patcher.patch_folder(veh_dir)
        for name, count in results.items():
            if count > 0:
                print(f"  {name}: {count} rows patched")
            total_patched += count
    except Exception as e:
        print(f"  Error: {e}")

print(f"\n总计补全: {total_patched} 行")
