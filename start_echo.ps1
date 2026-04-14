$dir = "C:\Users\jrsrl\Desktop\Echo2"

wt new-tab --title "Echo Voice" --startingDirectory $dir powershell -NoExit -Command "python echo.py" `; `
  new-tab --title "Echo Discord" --startingDirectory $dir powershell -NoExit -Command "python discord_echo.py" `; `
  new-tab --title "Echo Blink" --startingDirectory $dir powershell -NoExit -Command "python blink_watcher.py" `; `
  new-tab --title "Echo Moltbook" --startingDirectory $dir powershell -NoExit -Command "python moltbook_session.py"
