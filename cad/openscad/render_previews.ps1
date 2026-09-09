# render_previews.ps1 — render every CAD part to STL (cad/stl/) and a PNG
# preview (docs/img/).
#
#   powershell -ExecutionPolicy Bypass -File cad/openscad/render_previews.ps1
#   powershell ... -OpenSCAD "D:\tools\openscad.com"   # custom binary path
#
# Note: parts are selected via a generated wrapper .scad instead of -D
# 'PART="..."' because Windows PowerShell 5.1 mangles embedded quotes when
# invoking native commands.
param(
    [string]$OpenSCAD = "C:\Program Files\OpenSCAD\openscad.com",
    [string]$OutStl   = "$PSScriptRoot\..\stl",
    [string]$OutPng   = "$PSScriptRoot\..\..\docs\img"
)
$ErrorActionPreference = "Stop"

$sets = @(
    @{ File = "frame_brackets.scad";  Parts = @("corner_bracket", "motor_plate", "idler_mount") },
    @{ File = "gantry_carriage.scad"; Parts = @("toolhead_plate", "belt_clamp") },
    @{ File = "finger_module.scad";   Parts = @("finger_body", "deploy_arm") },
    @{ File = "button_plunger.scad";  Parts = @("plunger_base", "plunger_pin") },
    @{ File = "device_nest.scad";     Parts = @("corner_stop", "side_clamp") },
    @{ File = "camera_mounts.scad";   Parts = @("overhead_clamp", "toolcam_bracket") }
)

New-Item -ItemType Directory -Force -Path $OutStl, $OutPng | Out-Null
$failed = @()

foreach ($set in $sets) {
    foreach ($part in $set.Parts) {
        $wrapper = Join-Path $PSScriptRoot ".render_$part.scad"
        Set-Content -Path $wrapper -Value "_AT_PART = `"$part`";`ninclude <$($set.File)>" -Encoding ascii
        try {
            $stl = Join-Path $OutStl "$part.stl"
            $png = Join-Path $OutPng "$part.png"
            & $OpenSCAD -o $stl $wrapper | Out-Null
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path $stl) -or (Get-Item $stl).Length -le 84) {
                $failed += "$part (STL)"; continue
            }
            & $OpenSCAD -o $png --imgsize=1280,960 --colorscheme=Tomorrow `
                --camera=0,0,0,55,0,25,600 --autocenter --viewall $wrapper | Out-Null
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path $png) -or (Get-Item $png).Length -le 1000) {
                $failed += "$part (PNG)"
            } else {
                Write-Host "ok  $part"
            }
        } finally {
            Remove-Item $wrapper -ErrorAction SilentlyContinue
        }
    }
}

if ($failed) {
    Write-Host "render failed: $($failed -join ', ')"
    exit 1
}
Write-Host "all parts rendered."
