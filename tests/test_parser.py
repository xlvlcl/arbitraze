from app.providers.dobrybuk import extract_tables

HTML='''<html><body><table><tr><th>Godzina</th><th>Zdarzenie</th><th>Bonusy</th><th>1</th><th>X</th><th>2</th></tr><tr><td>20:45</td><td>Team A-Team B</td><td></td><td><img alt="Betclic">2.20</td><td><img alt="Fortuna">4.10</td><td><img alt="STS">4.20</td></tr></table></body></html>'''

def test_parse_dobrybuk_like_table():
    rows=extract_tables(HTML,'Piłka nożna','https://dobrybuk.pl/kursy')
    assert len(rows)==1
    assert rows[0]['event']=='Team A-Team B'
    assert rows[0]['quotes']['1'][0]['bookmaker']=='Betclic'
    assert rows[0]['quotes']['2'][0]['odds']==4.2

from app.providers.dobrybuk import _event_signature

def test_event_signature_dedupes_same_table_under_wrong_sport_label():
    base={'event':'Team A-Team B','market':'1X2','quotes':{
        '1':[{'bookmaker':'Betclic','odds':2.2}],
        'X':[{'bookmaker':'Fortuna','odds':3.4}],
        '2':[{'bookmaker':'STS','odds':4.2}],
    }}
    soccer=dict(base, sport='Piłka nożna')
    basketball=dict(base, sport='Koszykówka')
    assert _event_signature(soccer)==_event_signature(basketball)
