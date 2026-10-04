"""Run the local development server and open it in the default browser."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent.parent
URL = 'http://127.0.0.1:8000/'
os.chdir(ROOT)

def existing_project():
    try:
        with urllib.request.urlopen(URL, timeout=2) as response:
            return 'Rental Property Manager' in response.read(100000).decode('utf-8')
    except (OSError, ValueError):
        return False

def main():
    if existing_project():
        print('Rental Property Manager is already running at ' + URL)
        webbrowser.open(URL)
        return
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8000)) == 0:
            print('Port 8000 is occupied by another application.')
            print('Close it, or run: .venv\\Scripts\\python.exe manage.py runserver 127.0.0.1:8001')
            raise SystemExit(1)
    subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], check=True)
    print('Starting Rental Property Manager. Press Ctrl+C to stop.')
    server = subprocess.Popen([sys.executable, 'manage.py', 'runserver', '127.0.0.1:8000', '--noreload'])
    try:
        for _ in range(50):
            if server.poll() is not None:
                raise SystemExit(server.returncode or 1)
            if existing_project():
                webbrowser.open(URL)
                break
            time.sleep(0.1)
        server.wait()
    except KeyboardInterrupt:
        print('\nStopping the development server.')
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()

if __name__ == '__main__':
    main()
