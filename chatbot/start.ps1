# JOLT 车队助手 — 一键启动（PowerShell）
# 用法：右键“用 PowerShell 运行”，或在终端执行  ./chatbot/start.ps1
#       可透传参数： ./chatbot/start.ps1 --model opus --port 9000
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# 知识库不存在则先生成
if (-not (Test-Path (Join-Path $here "data\fleet_kb.json"))) {
  Write-Host "知识库不存在，正在生成 ..." -ForegroundColor Yellow
  python (Join-Path $here "build_kb.py")
}

Write-Host "启动桥接服务（Claude 订阅模式）..." -ForegroundColor Green
python (Join-Path $here "bridge.py") @args
