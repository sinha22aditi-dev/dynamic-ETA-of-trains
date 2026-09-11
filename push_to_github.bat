@echo off
setlocal
echo ========================================================
echo        DynamicRail - Push to GitHub Repository
echo        Repository: https://github.com/sinha22aditi-dev/dynamic-ETA-of-trains
echo ========================================================
echo.

set "GIT_EXE=C:\Users\Aditi sinha\AppData\Local\Programs\MinGit\cmd\git.exe"

if not exist "%GIT_EXE%" (
    where git >nul 2>&1
    if %errorlevel% equ 0 (
        set "GIT_EXE=git"
    ) else (
        echo [ERROR] Git executable not found.
        pause
        exit /b 1
    )
)

echo Checking Git status...
"%GIT_EXE%" status

echo.
echo If you have a GitHub Personal Access Token (PAT):
echo 1. Generate one at: https://github.com/settings/tokens (select 'repo' scope)
echo 2. Enter it when prompted below, or press Enter to push with default credentials.
echo.
set /p GITHUB_TOKEN="Enter GitHub Personal Access Token (or press Enter): "

if not "%GITHUB_TOKEN%"=="" (
    echo Pushing using Personal Access Token...
    "%GIT_EXE%" push https://sinha22aditi-dev:%GITHUB_TOKEN%@github.com/sinha22aditi-dev/dynamic-ETA-of-trains.git main
) else (
    echo Pushing to origin main...
    "%GIT_EXE%" push -u origin main
)

echo.
if %errorlevel% equ 0 (
    echo [SUCCESS] Repository pushed to GitHub successfully!
) else (
    echo [NOTICE] Push failed or requires authentication.
)
echo.
pause
