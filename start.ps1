$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
python app.py --mode fixture --catalog real

