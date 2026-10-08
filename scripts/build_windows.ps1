param(
    [string]$Distribution = "Ubuntu",
    [int]$Jobs = 8,
    [switch]$Reconfigure,
    [switch]$Test,
    [switch]$Synthetic
)
$ErrorActionPreference = "Stop"
function Invoke-CheckedNative([string]$Program, [string[]]$Arguments) {
    # Windows PowerShell 5 treats redirected native stderr as error records.
    # Compiler/test diagnostics do not imply failure; use the process status.
    $ErrorActionPreference = "Continue"
    & $Program @Arguments 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE." }
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$linuxRoot = (& wsl -d $Distribution --exec wslpath -a $projectRoot).Trim()
if ($LASTEXITCODE -ne 0) { throw "Could not resolve the project path in WSL." }
$buildArgs = @("-d", $Distribution, "--exec", "python3", "$linuxRoot/scripts/build_windows.py", "--jobs", "$Jobs")
if ($Reconfigure) { $buildArgs += "--reconfigure" }
Invoke-CheckedNative "wsl" $buildArgs
if ($Test -or $Synthetic) {
    $smokeArgs = @("$projectRoot/tests/native_smoke.py", "$projectRoot/build/native-dist/windows-x64/xemu_libretro.dll")
    if ($Synthetic) { $smokeArgs += "--synthetic" }
    Invoke-CheckedNative "python" $smokeArgs
}
