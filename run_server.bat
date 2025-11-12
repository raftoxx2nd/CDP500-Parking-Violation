@echo off
TITLE Parking Violation Server

echo Activating virtual environment...
CALL .\.venv\Scripts\activate.bat

echo Starting the dashboard server...
echo You can access the dashboard at http://localhost:8080
python src/server.py

echo Server has been stopped.
pause