<#
  start-mongo.ps1 — локальный MongoDB 7.0 для TrainWithBrain
  Поднимает mongod на 127.0.0.1:27017, если он ещё не запущен.
  Запуск:  powershell -ExecutionPolicy Bypass -File scripts\start-mongo.ps1
#>
param(
  [switch]$Stop,
  [switch]$Status
)

$ErrorActionPreference = 'Stop'

# --- Пути (относительно корня проекта) ---
$Root    = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Mongod  = Join-Path $Root '_mongo\bin\mongodb-win32-x86_64-windows-7.0.14\bin\mongod.exe'
$DataDir = Join-Path $Root '_mongo\data'
$LogFile = Join-Path $Root '_mongo\mongod.log'
$Port    = 27017

function Test-Port([int]$p) {
  try {
    $c = New-Object Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', $p)
    $c.Close()
    return $true
  } catch { return $false }
}

if ($Status) {
  $proc = Get-Process mongod -ErrorAction SilentlyContinue
  Write-Host ("mongod process : " + $(if ($proc) { "PID $($proc.Id)" } else { 'НЕ запущен' }))
  Write-Host ("порт $Port      : " + $(if (Test-Port $Port) { 'открыт' } else { 'закрыт' }))
  return
}

if ($Stop) {
  $proc = Get-Process mongod -ErrorAction SilentlyContinue
  if ($proc) { $proc | Stop-Process -Force; Write-Host 'mongod остановлен.' }
  else { Write-Host 'mongod не запущен.' }
  return
}

if (Test-Port $Port) {
  Write-Host "MongoDB уже слушает 127.0.0.1:$Port — ничего делать не нужно."
  return
}

if (-not (Test-Path $Mongod)) {
  Write-Error "Не найден mongod.exe: $Mongod"
}

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

Start-Process -FilePath $Mongod -ArgumentList @(
  '--dbpath', $DataDir,
  '--port', "$Port",
  '--bind_ip', '127.0.0.1',
  '--logpath', $LogFile,
  '--logappend'
) -WindowStyle Hidden

# Ждём готовности (до 30 c)
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  if (Test-Port $Port) { Write-Host "MongoDB запущен на 127.0.0.1:$Port (dbpath: $DataDir)"; return }
}
Write-Error "mongod не поднялся за 30 c — смотрите лог: $LogFile"
