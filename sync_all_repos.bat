@echo off
title Sync All GitHub Account Repositories
python "%~dp0uploader.py" --sync-all-github
pause

