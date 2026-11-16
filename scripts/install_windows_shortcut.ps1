$ErrorActionPreference = 'Stop'

$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Install the project dependencies in .venv before creating the shortcut.'
}

$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$path = Join-Path $desktop 'Обмен файлами.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($path)
if ((Test-Path -LiteralPath $path) -and $shortcut.TargetPath -ne $python) {
    throw "A different shortcut already uses the path $path"
}
$shortcut.TargetPath = $python
$shortcut.Arguments = '-m desktop_win.main'
$shortcut.WorkingDirectory = $project
$shortcut.Description = 'Обмен файлами между Windows и Android'
$shortcut.Save()
if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
    throw 'The shortcut could not be saved.'
}
Get-Item -LiteralPath $path
