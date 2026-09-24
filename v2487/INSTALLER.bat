@echo off
cd /d "%~dp0"
python -m pip install -U pip
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Installation terminee. Mets ton token dans .env puis lance DEMARRER.bat
pause
