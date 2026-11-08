from typing import Annotated, Any
from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints
from redis.exceptions import RedisError
from .parser import parse_line
from .storage import get_redis, STREAM, stats

Line = Annotated[str, StringConstraints(min_length=1, max_length=500)]
class IngestRequest(BaseModel):
    lines: list[Line] = Field(min_length=1, max_length=100)
class LineError(BaseModel):
    line: int
    reason: str
class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    errors: list[LineError]
class HealthResponse(BaseModel):
    status: str
    redis: bool
class SlowEvent(BaseModel):
    rid: str
    duration_ms: int
class StatsResponse(BaseModel):
    queued_total: int
    processed_total: int
    level: dict[str,int]
    service: dict[str,int]
    status: dict[str,int]
    top_slow: list[SlowEvent]
class EventResponse(BaseModel):
    id: str
    fields: dict[str,str]

router = APIRouter()
@router.get('/health', response_model=HealthResponse)
def health(r=Depends(get_redis)):
    r.ping()
    return {'status':'ok', 'redis':True}
@router.post('/ingest', response_model=IngestResponse)
def ingest(body: IngestRequest, r=Depends(get_redis)):
    events, errors = [], []
    for n, line in enumerate(body.lines, 1):
        try:
            events.append(parse_line(line,n))
        except ValueError as exc:
            errors.append({'line':n, 'reason':str(exc)})
    # MULTI/EXEC prevents a partially published valid batch on normal execution.
    if events:
        pipe = r.pipeline(transaction=True)
        for e in events:
            pipe.xadd(STREAM,e)
        pipe.execute()
    else:
        r.ping()
    return dict(accepted=len(events), rejected=len(errors), errors=errors)
@router.get('/stats', response_model=StatsResponse)
def get_stats(r=Depends(get_redis)):
    return stats(r)
@router.get('/events', response_model=list[EventResponse])
def events(limit: int=Query(default=10,ge=1,le=50), r=Depends(get_redis)):
    return [dict(id=eid,fields=e) for eid,e in r.xrevrange(STREAM,count=limit)]

app = FastAPI(title='LogPulse', version='1.0.0')
app.include_router(router)
@app.exception_handler(RedisError)
async def redis_error(request: Request, exc: RedisError):
    return JSONResponse(status_code=503,content={'error':{'code':'redis_unavailable','message':'Redis временно недоступен'}})
@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422,content={'error':{'code':'validation_error','message':'Неверная структура запроса','details':[{'loc':list(e['loc']),'message':e['msg']} for e in exc.errors()]}})
