# Compilación en Windows: ejecutable (PyInstaller) y versión portable en .zip.
#
# IMPORTANTE: este fichero se guarda en UTF-8 CON marca de orden de bytes (BOM):
# Windows PowerShell 5.1 lee sin BOM como ANSI y rompe los acentos.
#
# Uso: powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
# Sin PC con Windows: subir una etiqueta vX.Y.Z y lo compila GitHub (compilar.yml).

$Raiz = $PSScriptRoot | Split-Path -Parent
Set-Location $Raiz
$Version = (Select-String -Path "pyproject.toml" -Pattern '^version = "([^"]+)"').Matches[0].Groups[1].Value
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { Write-Host "[ERROR] No se encuentra Python"; exit 1 }
Write-Host "[INFO] Maquetador de programaciones $Version con $Python"

& $Python -m pip install --upgrade pip setuptools | Out-Null
& $Python -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] Fallo al instalar dependencias"; exit 1 }

Remove-Item -Recurse -Force build, "dist\MaquetadorProgramaciones", Output -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path Output | Out-Null

& $Python -m PyInstaller --noconfirm --clean MaquetadorProgramaciones.spec
$Exe = "dist\MaquetadorProgramaciones\MaquetadorProgramaciones.exe"
if (-not (Test-Path $Exe)) { Write-Host "[ERROR] PyInstaller no generó $Exe"; exit 1 }
Write-Host "[OK] Ejecutable: $Exe"

# El nombre del .zip lo espera la actualización automática (actualizaciones.py).
$Zip = "Output\MaquetadorProgramaciones-$Version-Windows-Portable.zip"
Compress-Archive -Path "dist\MaquetadorProgramaciones\*" -DestinationPath $Zip -CompressionLevel Optimal
Write-Host "[OK] Portable: $Zip"
