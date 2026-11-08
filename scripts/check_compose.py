"""Real isolated Docker Compose verification; requires a running Docker Engine.
Run from project root: python scripts/check_compose.py
No simulated results are produced. Failed commands stop the check.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'logpulse-check-' + uuid.uuid4().hex[:8]
OUT = ROOT / 'evidence' / PROJECT
OUT.mkdir(parents=True)
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
ENV = dict(os.environ, API_PORT=str(port), REDIS_URL='redis://redis:6379/0')
BASE = ['docker', 'compose', '-p', PROJECT, '-f', str(ROOT/'compose.yaml')]
transcript = OUT/'commands.txt'

def command(args):
    cp = subprocess.run(args, cwd=ROOT, env=ENV, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1200)
    with transcript.open('a') as f:
        f.write('$ ' + ' '.join(args) + '\n' + cp.stdout + '\nexit=' + str(cp.returncode) + '\n\n')
    print(cp.stdout, end='')
    cp.check_returncode()
    return cp.stdout

def compose(*args):
    return command(BASE + list(args))

def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=data, headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())

def ready():
    for _ in range(120):
        try:
            status, body = request('/health')
            if status == 200 and body['redis'] is True:
                return body
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    raise RuntimeError('API did not become ready')

def snapshot():
    status, body = request('/stats')
    assert status == 200
    return body

result = {'mode':'real Docker execution', 'project':PROJECT, 'port':port, 'passed':False}
attempted_start = False
try:
    command(['docker','info'])
    compose('config','--quiet')
    attempted_start = True
    compose('up','--build','-d')
    ready()
    compose('ps')
    compose('logs','--tail=50','api','worker','redis')
    compose('exec','-T','api','pytest','-q')
    lines=(ROOT/'data/sample.log').read_text().splitlines()
    status, body=request('/ingest', {'lines':lines})
    assert status == 200 and body['accepted']==36 and body['rejected']==7, body
    result['ingest']=body
    for _ in range(120):
        before=snapshot()
        if before['processed_total']==36:
            break
        time.sleep(.5)
    assert before['queued_total']==36 and before['processed_total']==36, before
    result['before']=before
    for args in [('XINFO','STREAM','logpulse:events'), ('XLEN','logpulse:events'), ('HGETALL','logpulse:stats:level'), ('HGETALL','logpulse:stats:service'), ('HGETALL','logpulse:stats:status'), ('ZREVRANGE','logpulse:slow','0','4','WITHSCORES'), ('XPENDING','logpulse:events','logpulse-workers')]:
        compose('exec','-T','redis','redis-cli',*args)
    # Exact required restart; compare every field, including the top five.
    compose('restart','redis')
    result['health_after_restart']=ready()
    after=snapshot()
    result['after']=after
    assert after == before, (before, after)
    # Additional controlled downtime makes the 503 observation deterministic.
    compose('stop','redis')
    status, body=request('/health')
    assert status==503, (status, body)
    result['during_stop']={'status':status,'body':body}
    assert request('/stats')[0]==503
    compose('start','redis')
    ready()
    assert snapshot()==before
    # Verify the existing worker is still consuming new events after recovery.
    line=lines[0].replace('rid=00000001','rid=abcdef01')
    assert request('/ingest', {'lines':[line]})[1]['accepted']==1
    for _ in range(120):
        resumed=snapshot()
        if resumed['processed_total']==37:
            break
        time.sleep(.5)
    assert resumed['processed_total']==37, resumed
    result['worker_resumed']=resumed
    result['passed']=True
finally:
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('\nEvidence:', OUT)
    if attempted_start:
        print('Test stack may be running. Stop without deleting its volume:')
        print(' '.join(BASE + ['down']))
    else:
        print('Preflight failed; no containers were started by this check.')
