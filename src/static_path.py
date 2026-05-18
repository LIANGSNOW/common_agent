from pathlib import Path


def get_root_path() -> Path:
    """获取项目根目录路径"""
    return Path(__file__).resolve().parent
