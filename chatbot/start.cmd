@echo off
chcp 65001 >nul
rem JOLT 车队助手 — 一键启动（双击即可）
if not exist "%~dp0data\fleet_kb.json" (
  echo 知识库不存在，正在生成 ...
  python "%~dp0build_kb.py"
)
echo 启动桥接服务（Claude 订阅模式）...
python "%~dp0bridge.py" %*
pause
