$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $ScriptDir "..\lib\power_runtime.py"
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
& $Python $Runtime install @args
exit $LASTEXITCODE
