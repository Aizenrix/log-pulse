import re
from datetime import datetime
from ipaddress import IPv4Address

MAIN = re.compile(r'(?P<timestamp>\S+) (?P<level>\S+) (?P<service>\S+) (?P<ip>\S+) (?P<method>\S+) (?P<path>\S+) (?P<status>\d{3}) (?P<duration_ms>-?\d+)ms rid=(?P<rid>\S+)')
TIME = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z')
RID = re.compile(r'[0-9a-fA-F]{8}')
PATH = re.compile(r'/[A-Za-z0-9_./?=&%~-]*')

def parse_line(line: str, number: int = 1) -> dict:
    def fail(reason):
        raise ValueError(f'Строка {number}: {reason}')
    m = MAIN.fullmatch(line)
    if not m:
        fail('неверный формат записи')
    d = m.groupdict()
    if not TIME.fullmatch(d['timestamp']):
        fail('timestamp должен иметь формат YYYY-MM-DDTHH:MM:SSZ')
    try:
        datetime.strptime(d['timestamp'], '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        fail('несуществующая дата или время')
    try:
        IPv4Address(d['ip'])
    except ValueError:
        fail('неверный IPv4')
    for field, choices in [('level', {'INFO','WARN','ERROR'}), ('service', {'auth','orders','payment'}), ('method', {'GET','POST','PUT','DELETE'})]:
        if d[field] not in choices:
            fail(f'недопустимое значение {field}')
    if not PATH.fullmatch(d['path']):
        fail('недопустимый путь')
    if not RID.fullmatch(d['rid']):
        fail('rid должен содержать 8 шестнадцатеричных символов')
    d['rid'] = d['rid'].lower()
    d['status'] = int(d['status'])
    d['duration_ms'] = int(d['duration_ms'])
    if not 100 <= d['status'] <= 599:
        fail('HTTP-код вне диапазона 100–599')
    if not 0 <= d['duration_ms'] <= 600000:
        fail('длительность вне диапазона 0–600000')
    return d
