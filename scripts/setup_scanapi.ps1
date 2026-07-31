param(
    [string]$Target = "benchmarks/external/scanapi",
    [string]$Commit = "eae3306fa85dd15e48934b3c9e703981a9f246fa"
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    git @args
    if ($LASTEXITCODE -ne 0) {
        throw "git command failed: git $args"
    }
}

if (Test-Path $Target) {
    Write-Host "ScanAPI checkout already exists at $Target"
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $Target) | Out-Null
    Invoke-Git clone --filter=blob:none --no-checkout https://github.com/scanapi/scanapi.git $Target
}

Invoke-Git -C $Target fetch origin
Invoke-Git -C $Target checkout $Commit

Write-Host "ScanAPI ready at $Target"
Invoke-Git -C $Target rev-parse HEAD
