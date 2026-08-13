# -*- coding: utf-8 -*-
"""Export DeskFlow user data (localStorage + registry settings) to JSON.

Runs the real app profile (%APPDATA%\\DeskFlow\\WebStorage) in dev mode,
dumps localStorage via JS, plus window settings from the registry.
Output: <project>/data/deskflow-data-export.json
"""
import json
import os
import sys
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DESKFLOW_TEST_MODULES", "todo")

import main as deskflow  # noqa: E402

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "deskflow-data-export.json"


def read_registry() -> dict:
    root = r"Software\DeskFlow\DesktopOrganizer"
    result = {}

    def read_key(path: str) -> None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                i = 0
                while True:
                    try:
                        name, value, kind = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    if kind == winreg.REG_MULTI_SZ:
                        value = [str(v) for v in value]
                    elif isinstance(value, bytes):
                        value = value.hex()
                    else:
                        value = str(value)
                    rel = path.replace(root + "\\", "") if path != root else ""
                    result[f"{rel}/{name}"] = value
                    i += 1
        except FileNotFoundError:
            pass

    read_key(root)
    for sub in ("widgetPosition", "widgetSize", "widgetManualSize"):
        read_key(root + "\\" + sub)
    return result


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    tray = deskflow.build_tray(app)
    controller = deskflow.DesktopController(app, tray)
    controller.startup()

    def dump() -> None:
        window = next(iter(controller.windows.values()), None)
        if window is None:
            print("ERROR: no widget window to dump from")
            app.quit()
            return
        js = (
            "JSON.stringify({keys: Object.keys(localStorage), "
            "values: Object.fromEntries(Object.entries(localStorage))})"
        )

        def done(out) -> None:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            payload = {}
            try:
                ls = json.loads(out or "{}")
                payload["localStorage"] = dict(zip(ls.get("keys", []), ls.get("values", {}).values())) if ls.get("keys") else ls.get("values", {})
            except Exception as error:
                print("localStorage parse failed:", error)
                payload["localStorage"] = {}
            payload["registry"] = read_registry()
            OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"exported -> {OUT}")
            print(f"localStorage keys: {len(payload['localStorage'])}")
            for key in sorted(payload["localStorage"]):
                value = payload["localStorage"][key]
                print(f"  {key}: {len(value)} chars")
            print(f"registry entries: {len(payload['registry'])}")
            for key in sorted(payload["registry"]):
                print(f"  {key} = {payload['registry'][key]!r}")
            app.quit()

        window.web.page().runJavaScript(js, done)

    QTimer.singleShot(6000, dump)
    QTimer.singleShot(20000, app.quit)
    app.exec()


if __name__ == "__main__":
    main()
