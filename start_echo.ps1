$dir   = "C:\Users\jrsrl\Desktop\Echo2"
$voice = "C:\Users\jrsrl\Desktop\Echos voice"
$py    = "C:\Python314\python.exe"

wt new-tab --title "XTTS Voice" --startingDirectory $dir powershell -NoExit -Command "conda activate xtts; python -m xtts_api_server --listen --port 5200 --device cuda --speaker-folder '$voice' --model-source local" `; `
  new-tab --title "Echo Server" --startingDirectory $dir powershell -NoExit -Command "& '$py' echo_server.py" `; `
  new-tab --title "Echo Discord" --startingDirectory $dir powershell -NoExit -Command "& '$py' discord_echo.py" `; `
  new-tab --title "Echo Blink" --startingDirectory $dir powershell -NoExit -Command "& '$py' blink_watcher.py" `; `
  new-tab --title "Echo Moltbook" --startingDirectory $dir powershell -NoExit -Command "& '$py' moltbook_session.py"
