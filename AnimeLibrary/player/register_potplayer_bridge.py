import json
import os
from pathlib import Path
import subprocess
import sys
import winreg

root = Path(os.environ['LOCALAPPDATA']) / 'AnimeLibrary'
bridge = (root / 'player/bridge/potplayer_bridge.py').resolve(strict=True)
pythonw = Path(sys.executable).with_name('pythonw.exe').resolve(strict=True)
command = subprocess.list2cmdline([str(pythonw), str(bridge)]) + ' "%1"'
with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\playbridge') as key:
    winreg.SetValueEx(key, '', 0, winreg.REG_SZ, 'URL:AnimeLibrary PotPlayer Bridge')
    winreg.SetValueEx(key, 'URL Protocol', 0, winreg.REG_SZ, '')
with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\playbridge\shell\open\command') as key:
    winreg.SetValueEx(key, '', 0, winreg.REG_SZ, command)
print(json.dumps({'command': command, 'bridge': str(bridge)}, ensure_ascii=False))
