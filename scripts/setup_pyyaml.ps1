param(
    [string]$Target = "benchmarks/external/pyyaml",
    [string]$Commit = "34a9bf82357f4952d8f194a5a31f1c39743652d0"
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    git @args
    if ($LASTEXITCODE -ne 0) {
        throw "git command failed: git $args"
    }
}

if (Test-Path $Target) {
    Write-Host "PyYAML checkout already exists at $Target"
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $Target) | Out-Null
    Invoke-Git clone --filter=blob:none https://github.com/yaml/pyyaml.git $Target
}

Invoke-Git -C $Target fetch origin
Invoke-Git -C $Target checkout $Commit

Write-Host "PyYAML ready at $Target"
Invoke-Git -C $Target rev-parse HEAD
