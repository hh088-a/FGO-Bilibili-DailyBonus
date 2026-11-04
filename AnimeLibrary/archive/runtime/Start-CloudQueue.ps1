$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath "$PSScriptRoot\STOP_ORGANIZE"){Remove-Item -LiteralPath "$PSScriptRoot\STOP_ORGANIZE"}
$organizer=Get-CimInstance Win32_Process | Where-Object {$_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -match 'library_watch\.py'}
if(-not $organizer){
    Start-Process -FilePath "$PSScriptRoot\venv\Scripts\pythonw.exe" -ArgumentList '-X','utf8',"`"$PSScriptRoot\library_watch.py`"" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
}
if(Test-Path -LiteralPath "$PSScriptRoot\CLOUD_QUOTA_STOP"){return}
if(Test-Path -LiteralPath "$PSScriptRoot\STOP_CLOUD"){Remove-Item -LiteralPath "$PSScriptRoot\STOP_CLOUD"}
$existing=Get-CimInstance Win32_Process | Where-Object {$_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -match 'cloud_queue\.py'}
if(-not $existing){
    Start-Process -FilePath "$PSScriptRoot\venv\Scripts\pythonw.exe" -ArgumentList '-X','utf8',"`"$PSScriptRoot\cloud_queue.py`"" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
}
