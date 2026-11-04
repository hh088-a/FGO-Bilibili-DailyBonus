"""Offline verification in a disposable copy; never imports the live installation."""
import ast
import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def run():
    sources = list((ROOT/'archive/runtime').glob('*.py')) + list((ROOT/'player').glob('*.py'))
    for source in sources:
        ast.parse(source.read_text(encoding='utf-8-sig'), filename=source.name)
    privacy = subprocess.run([sys.executable, str(ROOT/'tools/scan_release.py')],
                             cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    print(privacy.stdout.strip())
    if privacy.returncode:
        return privacy.returncode
    results = []
    with tempfile.TemporaryDirectory(prefix='anime-library-regression-') as td:
        copy = Path(td)/'repo'
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns('.git', '__pycache__',
            '.venv', 'venv', 'cache', 'data', 'downloads', 'generated', 'reports', '*.log', '*.lock'))
        for source in sources:
            py_compile.compile(str(copy/source.relative_to(ROOT)), doraise=True)
        guard = Path(td)/'guard'
        guard.mkdir()
        (guard/'sitecustomize.py').write_text(
            'import socket\n'
            'def blocked(*args, **kwargs):\n'
            '    raise RuntimeError("Network disabled during archive tests")\n'
            'socket.socket.connect=blocked\n'
            'socket.create_connection=blocked\n', encoding='utf-8')
        env = dict(os.environ, PYTHONPATH=str(guard), PYTHONIOENCODING='utf-8',
                   ANIME_CLOUD_ACCOUNT_ID='TEST_ACCOUNT', LOCALAPPDATA=str(Path(td)/'empty-local'))
        for script in sorted((copy/'tests').glob('test_*.py')):
            try:
                r = subprocess.run([sys.executable, str(script)], cwd=copy, env=env,
                                   capture_output=True, text=True, encoding='utf-8', timeout=45)
                ok = r.returncode == 0
                detail = (r.stdout+r.stderr).strip()
            except subprocess.TimeoutExpired:
                ok, detail = False, 'Timed out'
            results.append({'script': script.name, 'passed': ok})
            print(('PASS' if ok else 'FAIL') + ' ' + script.name)
            if not ok:
                print(detail)
    summary = {'source_files_parsed': len(sources), 'test_scripts': len(results),
               'passed': sum(r['passed'] for r in results), 'network_disabled': True,
               'live_services_contacted': False, 'results': results}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(r['passed'] for r in results) else 1

if __name__ == '__main__':
    raise SystemExit(run())
