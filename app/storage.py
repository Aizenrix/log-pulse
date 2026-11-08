import os
from redis import Redis
PREFIX = 'logpulse:'
STREAM = PREFIX + 'events'
GROUP = 'logpulse-workers'

def get_redis():
    return Redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379/0'), decode_responses=True, socket_connect_timeout=1, socket_timeout=3)

# Atomic update plus ACK: retry after a lost reply cannot count a Stream ID twice.
PROCESS = """
if redis.call('SISMEMBER', KEYS[5], ARGV[1]) == 0 then
 redis.call('HINCRBY', KEYS[1], ARGV[2], 1)
 redis.call('HINCRBY', KEYS[2], ARGV[3], 1)
 redis.call('HINCRBY', KEYS[3], ARGV[4], 1)
 if tonumber(ARGV[5]) >= 500 then
  redis.call('ZADD', KEYS[4], ARGV[5], ARGV[6])
 end
 redis.call('SADD', KEYS[5], ARGV[1])
end
return redis.call('XACK', KEYS[6], ARGV[7], ARGV[1])
"""

def process_event(r, event_id, e):
    return r.eval(PROCESS, 6, PREFIX+'stats:level', PREFIX+'stats:service', PREFIX+'stats:status', PREFIX+'slow', PREFIX+'processed', STREAM,
                  event_id, e['level'], e['service'], str(e['status']), str(e['duration_ms']), e['rid'], GROUP)

def stats(r):
    def counts(key):
        return {k:int(v) for k,v in r.hgetall(PREFIX+'stats:'+key).items()}
    level, service, status = counts('level'), counts('service'), counts('status')
    return dict(queued_total=r.xlen(STREAM), processed_total=sum(level.values()), level=level, service=service, status=status,
                top_slow=[dict(rid=k, duration_ms=int(v)) for k,v in r.zrevrange(PREFIX+'slow', 0, 4, withscores=True)])
