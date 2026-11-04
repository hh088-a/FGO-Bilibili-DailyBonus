"""Fail on common private artifacts and credential patterns; never echo values."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {'.md', '.py', '.ps1', '.json', '.txt', '.example', '.yml', '.yaml'}
DENIED_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.torrent', '.ass', '.ssa', '.srt', '.exe',
                     '.dll', '.zip', '.7z', '.db', '.sqlite', '.log', '.xml', '.pem', '.key'}
IGNORED_DIRS = {'.git', '__pycache__', '.venv', 'venv', 'cache', 'data', 'downloads',
                'generated', 'reports', 'logs', 'outputs'}
PATTERNS = {
    'github_credential': r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b',
    'private_user_path': r'(?i)C:[/\\]+Users[/\\]+(?!Public[/\\])[^/\\\s\"\x27]+',
    'hardcoded_cloud_account': r'cloudAccountId\s*=\s*[\"\x27]\d{5,}[\"\x27]',
    'tailscale_invitation': r'https://login\.tailscale\.com/admin/invite/[^\s\"\x27]+',
    'tailnet_host': r'\b[a-zA-Z0-9-]+\.tail[a-zA-Z0-9]+\.ts\.net\b',
    'private_tailscale_ip': r'\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b',
    'credential_literal': r'(?i)(?:password|api_key|access_token|secret)\s*[:=]\s*[\"\x27][a-zA-Z0-9_-]{12,}[\"\x27]',
    'magnet_link': r'magnet:\?xt=urn:btih:[a-zA-Z0-9]{20,}',
}

def scan():
    findings, count = [], 0
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if path.name in {'.gitignore', '.gitattributes', '.env.example'} or path.suffix in TEXT_EXTENSIONS:
            count += 1
            text = path.read_text(encoding='utf-8-sig')
            for kind, pattern in PATTERNS.items():
                if re.search(pattern, text):
                    findings.append({'file': rel.as_posix(), 'rule': kind})
        elif path.suffix.lower() in DENIED_EXTENSIONS:
            findings.append({'file': rel.as_posix(), 'rule': 'private_or_binary_artifact'})
        else:
            findings.append({'file': rel.as_posix(), 'rule': 'unreviewed_file_type'})
    print(json.dumps({'files_scanned': count, 'findings': findings}, ensure_ascii=False, indent=2))
    return 1 if findings else 0

if __name__ == '__main__':
    raise SystemExit(scan())
