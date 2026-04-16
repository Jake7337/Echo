$dir  = "C:\Users\jrsrl\Desktop\Echo2"
$voice = "C:\Users\jrsrl\Desktop\Echos voice"
$conda = "C:\Users\jrsrl\miniconda3\Scripts\conda.exe"

wt new-tab --title "XTTS Voice" --startingDirectory $dir powershell -NoExit -Command "& '$conda' run -n xtts python -m xtts_api_server --listen --port 5200 --device cuda --speaker-folder '$voice' --model-source local" `; `
  new-tab --title "Echo Server" --startingDirectory $dir powershell -NoExit -Command "python echo_server.py" `; `
  new-tab --title "Echo Discord" --startingDirectory $dir powershell -NoExit -Command "python discord_echo.py" `; `
  new-tab --title "Echo Blink" --startingDirectory $dir powershell -NoExit -Command "python blink_watcher.py" `; `
  new-tab --title "Echo Moltbook" --startingDirectory $dir powershell -NoExit -Command "python moltbook_session.py"
