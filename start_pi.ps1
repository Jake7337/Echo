while ($true) {
    Write-Host "Starting pi_speak.py on Pi..."
    ssh jake@192.168.68.84 "pkill -f pi_speak.py 2>/dev/null; sleep 1; PYTHONUNBUFFERED=1 python /home/jake/pi_speak.py 2>&1"
    Write-Host "pi_speak.py exited. Restarting in 5 seconds..."
    Start-Sleep 5
}
