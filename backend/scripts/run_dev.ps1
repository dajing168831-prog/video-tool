# 启动开发后端：把用户级环境变量刷进本进程，再跑 uvicorn。
# 密钥只存在于 Windows 用户环境变量里，不落项目文件。
#
# 变量名单只在 scripts\with_user_env.py 里维护一份 —— 这里不再抄一遍，
# 否则每加一个 key 就得改两个地方，漏一个就是"配置了但不生效"。
#
# 用法：
#   powershell -NoProfile -File scripts\run_dev.ps1 -Port 8911 -Bind 0.0.0.0
param(
    [int]$Port = 8911,
    [string]$Bind = "127.0.0.1",
    # 同时能跑几条出片任务。默认 2：一个人测够用，但局域网里三四个人一起点
    # 就会排队 —— 多人联调时传 -Workers 4（别开太大，会撞厂商并发上限）
    [int]$Workers = 2
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = "D:\venvs\video-tool\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$env:VT_CLONE_WORKERS = "$Workers"

Write-Host "启动 http://$Bind`:$Port"
& $py scripts\with_user_env.py $py -m uvicorn app.main:app --host $Bind --port $Port --log-level info
