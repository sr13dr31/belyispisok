$ErrorActionPreference = "Stop"

function Assert-Command {
    param([string]$Name, [string]$Hint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Host "Не найдено: $Name. $Hint"
        exit 1
    }
}

Assert-Command -Name "python" -Hint "Установите Python 3.8+ и добавьте в PATH."
Assert-Command -Name "npm" -Hint "Установите Node.js LTS и добавьте в PATH."

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$adminUi = Join-Path $root "admin-ui"

if (-not (Test-Path $adminUi)) {
    Write-Host "Папка admin-ui не найдена: $adminUi"
    exit 1
}

Write-Host "Запуск бота..."
Start-Process -WorkingDirectory $root -FilePath "python" -ArgumentList "bot.py"

Write-Host "Запуск админки..."
Start-Process -WorkingDirectory $adminUi -FilePath "npm" -ArgumentList "install"
Start-Process -WorkingDirectory $adminUi -FilePath "npm" -ArgumentList "run", "dev"

Write-Host "Готово. Бот и админка запускаются в отдельных процессах."
