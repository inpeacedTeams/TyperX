$ErrorActionPreference = 'Stop'
$work = Join-Path $env:TEMP 'TyperX-Interception'
$zip = Join-Path $work 'Interception.zip'
$extract = Join-Path $work 'files'
New-Item -ItemType Directory -Force -Path $work | Out-Null
Write-Host 'Downloading the official Interception 1.0.1 driver...'
Invoke-WebRequest 'https://github.com/oblitum/Interception/releases/download/v1.0.1/Interception.zip' -OutFile $zip
if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
Expand-Archive $zip -DestinationPath $extract -Force
$installer = Get-ChildItem $extract -Recurse -Filter 'install-interception.exe' | Select-Object -First 1
if (-not $installer) { throw 'install-interception.exe was not found in the official archive' }
Write-Host 'Windows will request administrator permission.'
$process = Start-Process $installer.FullName -ArgumentList '/install' -Verb RunAs -Wait -PassThru
if ($process.ExitCode -ne 0) { throw "Driver installer returned $($process.ExitCode)" }
Write-Host 'Driver installed. Reboot Windows before running TyperX.'
Read-Host 'Press Enter to close'
