@echo off
chcp 65001 >nul
title Fabrication de AUTO_FISHER.exe
cd /d "%~dp0"
echo.
echo  ==============================================
echo    Fabrication de AUTO_FISHER.exe  (1 seul fichier)
echo    A faire UNE fois, sur un PC Windows avec Python.
echo  ==============================================
echo.

set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" where python >nul 2>nul && set PY=python
if "%PY%"=="" (
  echo  [ERREUR] Python est introuvable.
  echo  Installe Python 3.11 ou 3.12 depuis https://www.python.org/downloads/
  echo  et COCHE la case "Add python.exe to PATH" pendant l'installation.
  echo  Puis relance ce fichier.
  pause
  exit /b 1
)

echo  [1/3] Preparation de l'environnement...
%PY% -m venv .venv_build || goto :erreur
call .venv_build\Scripts\activate.bat
python -m pip install --upgrade pip >nul

echo  [2/3] Installation des composants (quelques minutes)...
pip install -r requirements.txt pyinstaller || goto :erreur

echo  [3/3] Creation de l'exe (quelques minutes)...
python tools\build_exe.py || goto :erreur

copy /y dist\AUTO_FISHER.exe AUTO_FISHER.exe >nul
echo.
echo  ==============================================
echo    TERMINE !
echo    Le fichier est : %~dp0AUTO_FISHER.exe
echo    Donne-le a ton pote : double-clic, c'est tout.
echo  ==============================================
echo.
pause
exit /b 0

:erreur
echo.
echo  [ERREUR] La fabrication a echoue. Copie le texte ci-dessus et envoie-le moi.
pause
exit /b 1
