@echo off
rem Entry point for Windows Task Scheduler. Runs the bot once from this folder.
cd /d "%~dp0"
if not exist logs mkdir logs
python bot.py 2>> logs\errors.log
