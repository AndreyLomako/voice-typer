"""Платформенный слой: одна и та же программа, разные реализации под Windows, macOS и Linux.

Модуль ОС выбирается при импорте; тяжёлые зависимости каждой платформы
импортируются лениво, внутри функций.
"""
import sys

if sys.platform == "win32":
    from .windows import *  # noqa: F401,F403
    from .windows import NAME
elif sys.platform == "darwin":
    from .macos import *  # noqa: F401,F403
    from .macos import NAME
else:
    from .linux import *  # noqa: F401,F403
    from .linux import NAME

IS_WINDOWS = NAME == "windows"
IS_MAC = NAME == "macos"
IS_LINUX = NAME == "linux"
