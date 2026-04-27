@echo off
call C:\Users\jrsrl\miniconda3\Scripts\activate.bat xtts
python -m xtts_api_server --listen --port 5200 --device cuda --speaker-folder "C:\Users\jrsrl\Desktop\Echo Voice V2"
pause
