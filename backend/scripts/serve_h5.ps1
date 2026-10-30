# 把编译好的 H5 起成局域网可访问的静态服务。
#
# 用途：几台电脑/手机同时打开同一个地址测功能。
# 前置：H5 已构建（frontend\app 下 `npm run build:h5`）；后端已在跑（run_dev.ps1 -Bind 0.0.0.0）。
#
# 用法：
#   powershell -NoProfile -File scripts\serve_h5.ps1              # 8920，全部网卡
#   powershell -NoProfile -File scripts\serve_h5.ps1 -Port 8921
param(
    [int]$Port = 8920,
    [string]$Bind = "0.0.0.0"
)

$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path (Split-Path -Parent $root) "frontend\app\dist\build\h5"
if (-not (Test-Path (Join-Path $dist "index.html"))) {
    Write-Error "找不到 $dist\index.html，先跑 npm run build:h5"
    exit 1
}

$py = "D:\venvs\video-tool\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

# 列出本机所有 IPv4，方便直接把网址发给同事
$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -ExpandProperty IPAddress

Write-Host "H5 静态服务：$dist"
foreach ($ip in $ips) { Write-Host "  http://${ip}:$Port" }

# 不用 python -m http.server：它不发缓存头，浏览器会拿旧的 index.html，
# 于是"改了前端却看不到变化"。serve_h5.py 里只有两条缓存规则。
& $py (Join-Path $PSScriptRoot "serve_h5.py") $Port $Bind
