"""Read-only verification or sample ingestion against configured running API."""
import json
import os
import time
from pathlib import Path
import httpx
base=os.getenv('API_URL','http://127.0.0.1:8000')
with httpx.Client(base_url=base,timeout=10) as c:
    print('health', c.get('/health').status_code)
    lines=Path('data/sample.log').read_text().splitlines()
    print('ingest', c.post('/ingest',json={'lines':[x for x in lines if x]}).json())
    time.sleep(2)
    print('stats',json.dumps(c.get('/stats').json(),ensure_ascii=False,indent=2))
    print('invalid schema',c.post('/ingest',json={'lines':['']}).status_code)
    print('events',c.get('/events?limit=3').json())
