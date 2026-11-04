$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$qb="$root\qbittorrent\qbittorrent.exe"
if(-not (Get-Process qbittorrent -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $qb -ArgumentList '--no-splash','--webui-port=8098','--confirm-legal-notice' -WindowStyle Hidden
}
$stop=Join-Path $PSScriptRoot 'STOP'
if(Test-Path $stop){Remove-Item -LiteralPath $stop}
$ready=$false
for($attempt=0;$attempt -lt 20;$attempt++){
    try{Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8098/' -TimeoutSec 2|Out-Null;$ready=$true;break}catch{Start-Sleep -Seconds 1}
}
if(-not $ready){throw 'Downloader WebUI is not ready'}
if(Test-Path "$PSScriptRoot\data\state.json"){
    $credential=Import-Clixml "$root\config\qb.credential.xml"
    $session=New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8098/api/v2/auth/login' -Method Post -Body @{username=$credential.UserName;password=$credential.GetNetworkCredential().Password} -WebSession $session -Headers @{Referer='http://127.0.0.1:8098/'}|Out-Null
    $state=Get-Content "$PSScriptRoot\data\state.json" -Raw|ConvertFrom-Json
    $hashes=@($state.tasks.PSObject.Properties|ForEach-Object{if($_.Value.status -notin @('cloud_verified','abandoned','waiting_for_peers','source_replaced','needs_attention')){if($_.Value.source_hash){$_.Value.source_hash}else{$_.Name}}})
    if($hashes.Count){Invoke-RestMethod 'http://127.0.0.1:8098/api/v2/torrents/start' -Method Post -Body @{hashes=($hashes -join '|')} -WebSession $session -Headers @{Referer='http://127.0.0.1:8098/'}|Out-Null}
}
Start-Process -FilePath "$PSScriptRoot\venv\Scripts\pythonw.exe" -ArgumentList '-X','utf8',"`"$PSScriptRoot\batch.py`"",'run' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
Start-Process -FilePath "$PSScriptRoot\venv\Scripts\pythonw.exe" -ArgumentList '-X','utf8',"`"$PSScriptRoot\batch.py`"",'discover' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
if(Test-Path -LiteralPath "$PSScriptRoot\CLOUD_ONLY"){ & "$PSScriptRoot\Start-CloudQueue.ps1" }
