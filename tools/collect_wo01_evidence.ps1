param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$evidenceDir = Join-Path $projectRoot 'evidence/wo01-final'
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
New-Item -ItemType Directory -Force -Path 'runtime/tmp' | Out-Null
$env:TEMP = (Resolve-Path 'runtime/tmp').Path
$env:TMP = $env:TEMP
$env:UV_CACHE_DIR = Join-Path $projectRoot 'runtime/uv-cache'
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONIOENCODING = 'utf-8'

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCommand) {
    $uv = $uvCommand.Source
} else {
    $uv = Join-Path $projectRoot 'runtime/bootstrap-venv/Scripts/uv.exe'
}
if (-not (Test-Path -LiteralPath $uv)) { throw "uv executable missing: $uv" }

function Record-Gate {
    param([string]$Name, [string]$CommandText, [scriptblock]$Action)
    $outputLines = @(& $Action 2>&1 | ForEach-Object { $_.ToString() })
    $status = $LASTEXITCODE
    if ($null -eq $status) { $status = 0 }
    $record = "COMMAND: $CommandText`nINPUT: $projectRoot`n" + ($outputLines -join "`n") + "`nEXIT STATUS: $status`n"
    [System.IO.File]::WriteAllText((Join-Path $evidenceDir "$Name.txt"), $record, [System.Text.UTF8Encoding]::new($false))
    Write-Output "$Name exit=$status"
    if ($status -ne 0) { throw "$Name failed with exit $status" }
}

Record-Gate 'environment' 'uv --version; uv run --locked python -c "import sys,platform,PySide6,pyarrow,duckdb; print(sys.version); print(platform.platform()); print(''PySide6'',PySide6.__version__); print(''PyArrow'',pyarrow.__version__); print(''DuckDB'',duckdb.__version__)"' {
    & $uv --version
    & $uv run --locked python -c "import sys,platform,PySide6,pyarrow,duckdb; print(sys.version); print(platform.platform()); print('PySide6',PySide6.__version__); print('PyArrow',pyarrow.__version__); print('DuckDB',duckdb.__version__)"
}
Record-Gate 'ruff' 'uv run --locked ruff check src tests tools' {
    & $uv run --locked ruff check src tests tools
}
Record-Gate 'pytest' 'uv run --locked pytest -q' { & $uv run --locked pytest -q }
Record-Gate 'windows-chunk-replay' 'uv run --locked pytest -q tests/integration/test_recovery.py tests/replay/test_replay.py' {
    & $uv run --locked pytest -q tests/integration/test_recovery.py tests/replay/test_replay.py
}
Record-Gate 'safety-backpressure' 'uv run --locked pytest -q tests/unit/test_supplement.py tests/integration/test_backpressure.py tests/fault/test_faults.py' {
    & $uv run --locked pytest -q tests/unit/test_supplement.py tests/integration/test_backpressure.py tests/fault/test_faults.py
}
Record-Gate 'sbom-generation' 'uv run --locked python tools/generate_supply_chain.py' {
    & $uv run --locked python tools/generate_supply_chain.py
}
Record-Gate 'architecture-verification' 'uv run --locked python tools/verify_architecture.py' {
    & $uv run --locked python tools/verify_architecture.py
}
Record-Gate 'qml-shell' 'uv run --locked python tools/verify_qml_shell.py' {
    & $uv run --locked python tools/verify_qml_shell.py
}
Record-Gate 'headless-demo' 'uv run --locked batteryscope --headless-demo --runtime-dir runtime/wo01-final-demo' {
    & $uv run --locked batteryscope --headless-demo --runtime-dir runtime/wo01-final-demo
}
Record-Gate 'benchmark' 'uv run --locked python tools/benchmark_pipeline.py --samples-per-device 1000 --runtime-dir runtime/wo01-benchmark' {
    & $uv run --locked python tools/benchmark_pipeline.py --samples-per-device 1000 --runtime-dir runtime/wo01-benchmark
}
Write-Output 'WO01 evidence collection PASS'
