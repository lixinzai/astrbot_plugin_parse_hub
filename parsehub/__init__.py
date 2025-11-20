# 如果 ParseHub 类定义在 parsehub.py 里，就用下面这行：
from .parsehub import ParseHub

# 如果 ParseHub 类定义在 core.py 里，就改成：
# from .core import ParseHub

__all__ = ["ParseHub"]