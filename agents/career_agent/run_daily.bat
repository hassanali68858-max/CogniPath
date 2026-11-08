@echo off
REM Daily intake: bring new job postings into the database (no user needed)
cd /d "%~dp0src"
set PY="C:\Users\HP\Documents\CogniPath-Team\.venv\Scripts\python.exe"
%PY% gmail_fetch.py >> "%~dp0data\pipeline_log.txt" 2>&1
%PY% job_emails.py >> "%~dp0data\pipeline_log.txt" 2>&1
%PY% teamtailor_source.py >> "%~dp0data\pipeline_log.txt" 2>&1