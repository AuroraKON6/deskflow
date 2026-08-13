# DeskFlow · 序 · 桌面效率工具

Windows 桌面悬浮组件:今日待办 / 倒计时 / 文件收纳。PySide6 + QtWebEngine 原生外壳,界面层是单文件 HTML(`desktop-organizer-concepts/index.html`),每个模块一个独立透明悬浮窗口。

## 目录

- `desktop-organizer-app/` — Python 外壳源码(`main.py`)、构建脚本(`build.ps1`)、PyInstaller spec
- `desktop-organizer-concepts/` — 界面层(index.html + 概念渲染脚本)
- `desktop-organizer-dist/` — 构建产物(已被 .gitignore 排除,见 Releases)

## 构建

```powershell
cd desktop-organizer-app
.\build.ps1
```

产物位于 `desktop-organizer-dist\DeskFlow\DeskFlow.exe`。构建脚本已排除 PySide6 未使用的模块(Qt3D/Charts/Multimedia/Quick3D/虚拟键盘等),dist 约 320MB、296 个文件。

## 使用

- 双击 exe 启动,首次会弹出「桌面组件选择」对话框
- 每个模块是独立悬浮窗口:拖动标题栏移动、拖动窗口边缘调整大小
- 关闭窗口 = 收起,程序驻留系统托盘;托盘菜单可切换模块或彻底退出
- 数据(任务/倒计时/文件收纳)存在 `%APPDATA%\DeskFlow`

## 已知修复

- 手动尺寸模式下,嵌入窗口内 todo/countdown/files 三个页面全部堆叠渲染(CSS 优先级 bug,`.widget:not(.module-off)` 修复,2026-08-13)
