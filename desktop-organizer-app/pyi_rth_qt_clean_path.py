"""Prevent system/Anaconda Qt DLLs from leaking into the frozen app."""

import os
import sys
from pathlib import Path


bundle_root = Path(sys._MEIPASS)
qt_root = bundle_root / "PySide6"
windows_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
os.environ["PATH"] = os.pathsep.join(
    str(path)
    for path in (qt_root, bundle_root, windows_root / "System32", windows_root)
)
os.environ["QT_PLUGIN_PATH"] = str(qt_root / "plugins")
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(qt_root / "plugins" / "platforms")
os.environ["QML2_IMPORT_PATH"] = str(qt_root / "qml")
