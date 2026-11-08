import pytest
from app.parser import parse_line, TIME, RID, PATH
BASE='2026-10-20T12:34:56Z INFO auth 192.0.2.10 POST /api/login 200 43ms rid=ab12cd34'
def test_valid():
    assert parse_line(BASE)['duration_ms']==43
@pytest.mark.parametrize('old,new,reason', [('2026-10-20','2026-02-30','дата'),('192.0.2.10','999.0.0.1','IPv4'),('INFO','DEBUG','level'),('200 ','600 ','HTTP'),('43ms','-1ms','длительность'),('ab12cd34','bad','rid'),('auth','other','service'),('POST','PATCH','method'),('/api/login','abc','путь'),('43ms','600001ms','длительность'),('Z INFO','+00:00 INFO','timestamp')])
def test_invalid(old,new,reason):
    with pytest.raises(ValueError,match=reason): parse_line(BASE.replace(old,new),7)
def test_time_regex():
    assert TIME.fullmatch('2026-10-20T12:34:56Z')
    assert not TIME.fullmatch('2026-10-20')
def test_rid_regex():
    assert RID.fullmatch('aB123456')
    assert not RID.fullmatch('zz123456')
def test_path_regex():
    assert PATH.fullmatch('/api/test?q=1')
    assert not PATH.fullmatch('/bad path')
def test_empty():
    with pytest.raises(ValueError,match='Строка 9'): parse_line('',9)
def test_sample():
    from pathlib import Path
    lines=Path('data/sample.log').read_text().splitlines()
    good=[]
    for line in lines:
        try: good.append(parse_line(line))
        except ValueError: pass
    assert len(lines)>=40 and len(lines)-len(good)>=5
    assert len({e['rid'] for e in good})==len(good)
