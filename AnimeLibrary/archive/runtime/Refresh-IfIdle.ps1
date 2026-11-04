$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$url='http://127.0.0.1:8097'
$headers=@{Authorization='MediaBrowser Client="AnimeLibrary Tools", Device="Windows PC", DeviceId="anime-library-tools", Version="1.0"'}
$authenticated=$false
try{
    $credential=Import-Clixml -LiteralPath "$root\config\admin.credential.xml"
    $auth=Invoke-RestMethod "$url/Users/AuthenticateByName" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{Username=$credential.UserName;Pw=$credential.GetNetworkCredential().Password}|ConvertTo-Json -Compress) -TimeoutSec 5
    $headers.Authorization+=', Token="'+$auth.AccessToken+'"'
    $authenticated=$true
    $tasks=Invoke-RestMethod "$url/ScheduledTasks" -Headers $headers -TimeoutSec 5
    $scan=$tasks|Where-Object {$_.Key -eq 'RefreshLibrary' -and $_.State -eq 'Running'}|Select-Object -First 1
    if($scan){@{status='running';progress=$scan.CurrentProgressPercentage}|ConvertTo-Json -Compress}
    else{
        Invoke-RestMethod "$url/Library/Refresh" -Method Post -Headers $headers -TimeoutSec 5|Out-Null
        @{status='refreshed'}|ConvertTo-Json -Compress
    }
}catch{@{status='unavailable'}|ConvertTo-Json -Compress}
finally{if($authenticated){try{Invoke-RestMethod "$url/Sessions/Logout" -Method Post -Headers $headers -TimeoutSec 3|Out-Null}catch{}}}
