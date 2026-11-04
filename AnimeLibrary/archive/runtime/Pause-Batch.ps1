$ErrorActionPreference='Stop'
'pause'|Set-Content -LiteralPath "$PSScriptRoot\STOP_ORGANIZE"
'pause'|Set-Content -LiteralPath "$PSScriptRoot\STOP_CLOUD"
'pause'|Set-Content -LiteralPath "$PSScriptRoot\STOP"
$credential=Import-Clixml (Join-Path (Split-Path $PSScriptRoot -Parent) 'config\qb.credential.xml')
$session=New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8098/api/v2/auth/login' -Method Post -Body @{username=$credential.UserName;password=$credential.GetNetworkCredential().Password} -WebSession $session -Headers @{Referer='http://127.0.0.1:8098/'}|Out-Null
$state=Get-Content "$PSScriptRoot\data\state.json" -Raw|ConvertFrom-Json
$hashes=@($state.tasks.PSObject.Properties|ForEach-Object{if($_.Value.status -ne 'cloud_verified'){if($_.Value.source_hash){$_.Value.source_hash}else{$_.Name}}})
if($hashes.Count){Invoke-RestMethod 'http://127.0.0.1:8098/api/v2/torrents/stop' -Method Post -Body @{hashes=($hashes -join '|')} -WebSession $session -Headers @{Referer='http://127.0.0.1:8098/'}|Out-Null}
Write-Host 'Batch scheduling and managed downloads paused. Any in-progress upload will finish its current operation.'
