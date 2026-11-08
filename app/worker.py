import logging
import os
import time
from redis.exceptions import RedisError, ResponseError
from .storage import get_redis, STREAM, GROUP, process_event
logging.basicConfig(level=logging.INFO)

def ensure_group(r):
    try:
        r.xgroup_create(STREAM, GROUP, id='0', mkstream=True)
    except ResponseError as exc:
        if 'BUSYGROUP' not in str(exc):
            raise

def run():
    r = get_redis()
    consumer = os.getenv('CONSUMER_NAME', 'worker-1')
    while True:
        try:
            ensure_group(r)
            # First recover this consumer's pending records, then abandoned records.
            pending = r.xreadgroup(GROUP, consumer, {STREAM:'0'}, count=100)
            for _, events in pending:
                for eid, e in events:
                    process_event(r, eid, e)
            cursor = '0-0'
            while True:
                claimed = r.xautoclaim(STREAM, GROUP, consumer, 30000, start_id=cursor, count=100)
                cursor = claimed[0]
                for eid, e in claimed[1]:
                    process_event(r, eid, e)
                if cursor == '0-0':
                    break
            for _, events in r.xreadgroup(GROUP, consumer, {STREAM:'>'}, count=100, block=1000):
                for eid, e in events:
                    process_event(r, eid, e)
        except RedisError:
            logging.warning('Redis unavailable; retry in one second')
            time.sleep(1)

if __name__ == '__main__':
    run()
