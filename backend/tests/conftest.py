"""pytest 配置: 将 backend 根目录加入 sys.path, 保证可导入 app 包。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
