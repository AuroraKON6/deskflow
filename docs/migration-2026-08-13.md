# 迁移记录

2026-08-13 项目整体从 `C:\Users\K-ON的学习本\Documents\设计\` 迁移到 `E:\DeskFlow\`。

## 迁移时修复的引用

- 开机自启注册表 `HKCU\...\Run\DeskFlow` → 已指向 `E:\DeskFlow\desktop-organizer-dist\DeskFlow\DeskFlow.exe`(备份在 `%TEMP%\run_backup.reg`)
- `DeskFlow.spec` 里的 C 盘硬编码路径:由 `build.ps1` 每次运行 PyInstaller 时自动重写,无需手动改
- `build.ps1` 的 venv 路径、ProjectRoot:动态计算,自动适配新位置

## 旧位置残留

`C:\Users\K-ON的学习本\Documents\设计\` 只剩 `room_redesign\`(空目录,与 DeskFlow 无关)。

## 注意

- 用户数据仍在 `%APPDATA%\DeskFlow`(注册表 HKCU\Software\DeskFlow),不在项目目录,迁移不受影响
