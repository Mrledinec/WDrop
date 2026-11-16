param([string]$InnoCompiler)
$ErrorActionPreference = 'Stop'

$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.venv\Scripts\python.exe'
$build = Join-Path $project '.windows-build'
$dist = Join-Path $project 'dist'
if (-not $InnoCompiler) {
    $InnoCompiler = Join-Path $build 'inno\ISCC.exe'
    if (-not (Test-Path -LiteralPath $InnoCompiler -PathType Leaf)) {
        $InnoCompiler = (Get-Command ISCC.exe -ErrorAction Stop).Source
    }
}
$InnoCompiler = (Resolve-Path -LiteralPath $InnoCompiler).Path

Push-Location -LiteralPath $project
try {
    $version = & $python -c 'from desktop_win.update import VERSION; print(VERSION)'
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') {
        throw 'Unable to read the application version.'
    }
    $bundleArgs = @(
        '--noconfirm', '--windowed', '--onedir', '--noupx', '--name', 'LocalTransfer',
        '--distpath', "$build\bundle", '--workpath', "$build\work", '--specpath', $build,
        '--paths', $project, '--hidden-import', 'uvicorn.logging',
        '--hidden-import', 'uvicorn.loops.auto', '--hidden-import', 'uvicorn.protocols.http.auto',
        '--hidden-import', 'uvicorn.protocols.websockets.auto', '--hidden-import', 'uvicorn.lifespan.on',
        'desktop_win\main.py'
    )
    & $python -m PyInstaller @bundleArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # Qt imports the Windows ICU API. A third-party ICU from PATH can have different exports.
    $bundle = Join-Path $build 'bundle\LocalTransfer'
    Get-ChildItem -LiteralPath (Join-Path $bundle '_internal') -File |
        Where-Object Name -Match '^(icuuc|icudt\d+)\.dll$' |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName }

    New-Item -ItemType Directory -Path $dist -Force | Out-Null
    $compilerArgs = @("/DAppVersion=$version", "/DBundleDir=$bundle", "/O$dist", "$PSScriptRoot\windows_setup.iss")
    & $InnoCompiler @compilerArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Get-Item -LiteralPath (Join-Path $dist "LocalTransfer-Setup-$version.exe")
} finally {
    Pop-Location
}
