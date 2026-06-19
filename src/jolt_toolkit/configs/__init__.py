"""
共享配置目录。

提供 CONFIGS_DIR 常量和 get_config_path() 便捷函数，
供三个子包统一定位 vehicles.json / pipelines.json / plot_config.json。
"""

from pathlib import Path

CONFIGS_DIR: Path = Path(__file__).resolve().parent

def get_config_path(name: str) -> Path:
    """返回 configs/ 下指定文件名的绝对路径。"""
    return CONFIGS_DIR / name
