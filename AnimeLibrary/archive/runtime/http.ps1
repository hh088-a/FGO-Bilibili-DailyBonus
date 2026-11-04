param([Parameter(Mandatory=$true)][string]$Url,[Parameter(Mandatory=$true)][string]$OutputPath,[string]$BodyPath='')
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$headers=@{'User-Agent'='AnimeLibrary/1.0 (personal media catalog; Windows)'}
if($BodyPath){
  Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Post -ContentType 'application/json; charset=utf-8' -Body ([IO.File]::ReadAllBytes($BodyPath)) -Headers $headers -OutFile $OutputPath -TimeoutSec 35 | Out-Null
} else {
  Invoke-WebRequest -UseBasicParsing -Uri $Url -Headers $headers -OutFile $OutputPath -TimeoutSec 35 | Out-Null
}
