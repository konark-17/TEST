@echo off
setlocal enabledelayedexpansion
title Publish to GitHub - Automated Commit Engine
cls
echo =================================================================
echo       PUBLISH AUTOMATED GITHUB UPLOADER TO A NEW REPOSITORY
echo =================================================================
echo.
echo Recommended Repository Names:
echo   [1] GitStreak      (Punchy, memorable, perfect for streak automation)
echo   [2] CommitFlow     (Clean, developer workflow branding)
echo   [3] GitPacer       (Reflects pacing commits day by day)
echo   [4] AutoGit-Sync   (Technical, multi-repo synchronization)
echo.
echo Suggested GitHub Description:
echo   "Automated multi-repo GitHub commit scheduler, streak spreader,
echo    and FastAPI dashboard with Windows Task Scheduler integration."
echo.
echo -----------------------------------------------------------------
echo Step 1: Create a new repository on GitHub (at https://github.com/new)
echo         - Name: GitStreak (or choose your preferred name)
echo         - Visibility: Public or Private
echo         - Leave 'Add a README file' UNCHECKED
echo -----------------------------------------------------------------
echo.
set /p REPONAME="Enter your new repository name [Default: GitStreak]: "
if "%REPONAME%"=="" set REPONAME=GitStreak

set TARGET_URL=https://github.com/konark-17/%REPONAME%.git

echo.
echo Target remote URL: %TARGET_URL%
echo.
set /p CONFIRM="Ready to set remote and push main branch? (Y/N) [Default: Y]: "
if "%CONFIRM%"=="" set CONFIRM=Y
if /i not "%CONFIRM%"=="Y" (
    echo.
    echo Operation cancelled by user.
    pause
    exit /b 0
)

echo.
echo [*] Updating git remote 'origin' to %TARGET_URL%...
git remote set-url origin %TARGET_URL%
if errorlevel 1 (
    echo [*] Remote 'origin' not found, adding it...
    git remote add origin %TARGET_URL%
)

echo.
echo [*] Ensuring branch is 'main'...
git branch -M main

echo.
echo [*] Pushing 'main' branch to GitHub (%TARGET_URL%)...
git push -u origin main
if errorlevel 1 (
    echo.
    echo [ERROR] Git push failed!
    echo Possible reasons:
    echo   1. The repository 'konark-17/%REPONAME%' has not been created on GitHub yet.
    echo      Go to https://github.com/new and create it first!
    echo   2. Authentication failed (check your GitHub credentials or Personal Access Token).
    echo.
    echo You can retry anytime by running publish_to_github.bat again.
    echo.
    pause
    exit /b 1
)

echo.
echo =================================================================
echo   SUCCESS! Project successfully published to GitHub!
echo   Repository URL: https://github.com/konark-17/%REPONAME%
echo =================================================================
echo.
pause
