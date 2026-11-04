"""Per-user playbridge URI launcher. Opens only anime videos on the X: mount."""
import datetime
import json
import ntpath
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote

# Resolve from the installed script, including the desktop app's MSIX path.
# External desktop processes do not inherit Codex's virtual LocalAppData view.
ROOT = Path(__file__).resolve().parents[2]
PLAYER = ROOT / 'player/PotPlayer/PotPlayerMini64.exe'
ALLOWED_ROOT = r'X:\动漫'
EXTENSIONS = {'.mkv', '.mp4', '.avi', '.m4v', '.ts', '.m2ts', '.webm', '.mov'}


def parse_uri(uri):
    if not isinstance(uri, str) or not uri.lower().startswith('playbridge://'):
        raise ValueError('Invalid protocol')
    raw = uri[len('playbridge://'):]
    # Empty URI authority avoids an encoded drive colon in Qt's host parser.
    if raw.startswith('/'):
        raw = raw[1:]
    if '?' in raw or '#' in raw:
        raise ValueError('Remote streams and query parameters are disabled')
    path = unquote(raw, encoding='utf-8', errors='strict').replace('/', '\\')
    if any(c in path for c in '\r\n\x00"<>|?*') or any(ord(c) < 32 for c in path):
        raise ValueError('Invalid path characters')
    if ':' in path[2:] or not path.lower().startswith('x:\\'):
        raise ValueError('Only the X: mount is allowed')
    if '..' in path.split('\\'):
        raise ValueError('Parent traversal is disabled')
    path = ntpath.normpath(path)
    if ntpath.commonpath([ALLOWED_ROOT.lower(), path.lower()]) != ALLOWED_ROOT.lower():
        raise ValueError('File must be inside the anime library')
    if ntpath.splitext(path)[1].lower() not in EXTENSIONS:
        raise ValueError('Unsupported video file')
    return path


def main():
    log = ROOT / 'logs/potplayer-bridge.jsonl'
    log.parent.mkdir(parents=True, exist_ok=True)
    record = {'time': datetime.datetime.now().isoformat(timespec='seconds')}
    try:
        if len(sys.argv) != 2:
            raise ValueError('Expected one URI')
        video = parse_uri(sys.argv[1])
        if not PLAYER.is_file():
            raise FileNotFoundError('PotPlayer runtime is missing')
        if not Path(video).is_file():
            raise FileNotFoundError('Video is unavailable on the X: mount')
        # Argument list (no shell) preserves Chinese names, spaces, and ampersands.
        child = subprocess.Popen([str(PLAYER), video, '/current'], cwd=PLAYER.parent)
        record.update(status='launched', video=video, pid=child.pid)
    except Exception as exc:
        record.update(status='error', error=str(exc))
    with log.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
