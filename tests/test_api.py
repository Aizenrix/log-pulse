import fakeredis
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError
from app.main import app
from app.storage import get_redis, STREAM, GROUP, process_event
from app.worker import ensure_group
from tests.test_parser import BASE
@pytest.fixture
def context():
    r=fakeredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis]=lambda:r
    with TestClient(app) as c: yield c,r
    app.dependency_overrides.clear()
def test_mixed(context):
    c,r=context
    response=c.post('/ingest',json={'lines':[BASE]*3+['bad','also bad']})
    assert response.status_code==200
    assert response.json()['accepted']==3 and response.json()['rejected']==2
    assert len(response.json()['errors'])==2 and r.xlen(STREAM)==3
@pytest.mark.parametrize('payload',[{}, {'lines':[]},{'lines':['x']*101},{'lines':['']},{'lines':['a'*501]},{'lines':'oops'}])
def test_schema(context,payload):
    assert context[0].post('/ingest',json=payload).status_code==422
def test_health(context):
    assert context[0].get('/health').json()=={'status':'ok','redis':True}
def test_down(context):
    class Down:
        def ping(self): raise ConnectionError('private detail')
    app.dependency_overrides[get_redis]=lambda:Down()
    response=context[0].get('/health')
    assert response.status_code==503 and 'private detail' not in response.text
def drain(r):
    ensure_group(r)
    events=r.xreadgroup(GROUP,'test',{STREAM:'>'},count=100)[0][1]
    for eid,e in events: process_event(r,eid,e)
    return events
def test_counts(context):
    c,r=context
    c.post('/ingest',json={'lines':[BASE]*3})
    assert c.get('/stats').json()['processed_total']==0
    drain(r)
    s=c.get('/stats').json()
    assert s['processed_total']==3 and s['level']=={'INFO':3} and s['service']=={'auth':3} and s['status']=={'200':3}
    assert r.xpending(STREAM,GROUP)['pending']==0
def test_top(context):
    c,r=context
    c.post('/ingest',json={'lines':[BASE.replace('43ms',f'{n*100}ms').replace('ab12cd34',f'{n:08x}') for n in range(10)]})
    drain(r)
    assert [e['duration_ms'] for e in c.get('/stats').json()['top_slow']]==[900,800,700,600,500]
def test_idempotent(context):
    c,r=context
    c.post('/ingest',json={'lines':[BASE]})
    eid,e=drain(r)[0]
    process_event(r,eid,e)
    assert c.get('/stats').json()['processed_total']==1
@pytest.mark.parametrize('limit',[0,51])
def test_limit(context,limit):
    assert context[0].get(f'/events?limit={limit}').status_code==422
def test_events(context):
    c,r=context
    c.post('/ingest',json={'lines':[BASE]})
    assert c.get('/events').json()[0]['fields']['rid']=='ab12cd34'
def test_openapi(context):
    c,r=context
    assert c.get('/docs').status_code==200
    assert '/ingest' in c.get('/openapi.json').json()['paths']
