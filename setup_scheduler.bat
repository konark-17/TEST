@echo off
title GitHub Daily Uploader - Scheduler Setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_scheduler.ps1" -Action menu
