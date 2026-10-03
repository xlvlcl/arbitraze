from __future__ import annotations
import asyncio,time,socket
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from .config import settings,ROOT
from .models import Quote
from .surebet import detect
from .providers.dobrybuk import DobryBukProvider
from .state import State
from .telegram import send,discover,render

state=State(ROOT/'data'/'state.json')
provider=DobryBukProvider(settings)
scan_task=None

# Bookmaker payout defaults. 1.0 = no stake tax deducted from the bet. 0.88 = 12% stake tax deducted.
DEFAULT_FACTORS={
    'Betclic':1.0,
    'Fortuna':1.0,
    'eFortuna':1.0,
    'Superbet':0.88,
    'STS':0.88,
    'Forbet':0.88,
    'LVBet':0.88,
    'ETOTO':0.88,
    'eToto':0.88,
    'Betfan':0.88,
    'Fuksiarz':0.88,
    'TotalBet':0.88,
    'Total Bet':0.88,
    'Betters':0.88,
    'LeBull':0.88,
    'AdmiralBet':0.88,
    'BetSport':0.88,
    'Betsport':0.88,
    'ComeOn':0.88,
    'PZBuk':0.88,
}

def dedupe_surebets(items):
    # Same arbitraż can be emitted twice when the source renders a table in
    # more than one navigation state. Keep the best copy only.
    unique={}
    for arb in items:
        key=(arb.event.strip().lower(),arb.market.strip().lower(),tuple(sorted((x.selection.strip().lower(),x.bookmaker.strip().lower(),round(x.odds,3)) for x in arb.legs)))
        prev=unique.get(key)
        if prev is None or arb.profit_pct>prev.profit_pct:
            unique[key]=arb
    return list(unique.values())

def factors():
    d=dict(DEFAULT_FACTORS); d.update(settings.bookmaker_payout_factors or {}); return d

async def scan_once():
    started=time.time(); found=[]; errors=[]
    try:
        events,errors=await provider.scan_all(settings.sports)
        for e in events:
            qdict={}
            for sel,items in e['quotes'].items():
                for x in items:
                    if x['bookmaker']=='Unknown': continue
                    qdict.setdefault(sel,[]).append(Quote(x['selection'],x['odds'],x['bookmaker'],x['observed_at'],x['source_url'],x.get('bookmaker_url','')))
            found.extend(detect(e['event'],e['sport'],e['market'],qdict,settings.bankroll,factors(),settings.min_profit_pct,settings.max_quote_age_seconds))
        found=dedupe_surebets(found)
        found.sort(key=lambda a:a.profit_pct,reverse=True)
        # Confirmation pass only when a candidate exists. Require the same arb to appear again
        # after a short delay before sending an instant alert.
        confirmed=[]
        if found:
            await asyncio.sleep(max(1, min(3, int(settings.recheck_delay_seconds))))
            confirm_events,confirm_errors=await provider.scan_all(sorted({a.sport for a in found}))
            confirm_map={}
            for e in confirm_events:
                qdict={}
                for sel,items in e['quotes'].items():
                    for x in items:
                        qdict.setdefault(sel,[]).append(Quote(x['selection'],x['odds'],x['bookmaker'],x['observed_at'],x['source_url'],x.get('bookmaker_url','')))
                for a in detect(e['event'],e['sport'],e['market'],qdict,settings.bankroll,factors(),settings.min_profit_pct,settings.max_quote_age_seconds):
                    confirm_map[a.key()]=a
            confirmed=dedupe_surebets([confirm_map[a.key()] for a in found if a.key() in confirm_map])
            errors += [f'Potwierdzenie: {e}' for e in confirm_errors]
        state.latest=confirmed[:100] if found else []
        state.last_scan=time.time(); state.stats={'events':len(events),'candidates':len(found),'surebets':len(confirmed),'elapsed_seconds':round(time.time()-started,2),'interval_seconds':settings.scan_interval_seconds}
        for arb in confirmed:
            if await state.should_alert(arb.key(),arb.profit_pct,settings.dedupe_minutes) and settings.telegram_token and settings.telegram_chat_id:
                try: await send(settings.telegram_token,settings.telegram_chat_id,render(arb))
                except Exception as e: errors.append(f'Telegram: {e}')
        state.errors=errors
    except Exception as e:
        state.errors=[str(e)]+errors

async def loop():
    while True:
        t=time.time(); await scan_once(); await asyncio.sleep(max(5,settings.scan_interval_seconds-(time.time()-t)))

@asynccontextmanager
async def lifespan(app):
    global scan_task
    await provider.start(); scan_task=asyncio.create_task(loop()); yield
    scan_task.cancel()
    try: await scan_task
    except asyncio.CancelledError: pass
    await provider.stop()

app=FastAPI(title='Surebet Alert',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=str(ROOT/'static')),name='static')

@app.get('/',response_class=HTMLResponse)
async def index(): return (ROOT/'static'/'index.html').read_text('utf-8')
@app.get('/setup',response_class=HTMLResponse)
async def setup(): return (ROOT/'static'/'setup.html').read_text('utf-8')
@app.get('/api/status')
async def status():
    s=state.snapshot(); s['settings']=settings.public(); s['server_urls']=urls(); return s
@app.post('/api/scan-now')
async def scan_now(): await scan_once(); return {'ok':True}
@app.get('/api/surebets')
async def surebets(): return [x.to_dict() for x in state.latest]
@app.post('/api/settings')
async def save_settings(payload:dict):
    allowed={'bankroll','min_profit_pct','scan_interval_seconds','max_quote_age_seconds','dedupe_minutes','sports','telegram_token','telegram_chat_id','bookmaker_payout_factors'}
    updates={k:v for k,v in payload.items() if k in allowed}
    if 'sports' in updates and not isinstance(updates['sports'],list): raise HTTPException(400,'sports musi być listą')
    settings.save(updates); return {'ok':True,'settings':settings.public()}
@app.post('/api/telegram/discover')
async def tg_discover(payload:dict):
    token=str(payload.get('token') or settings.telegram_token)
    if not token:return {'ok':False,'message':'Brak tokena'}
    chat=await discover(token)
    if not chat:return {'ok':False,'message':'Wyślij /start lub wiadomość do bota i spróbuj ponownie.'}
    settings.save({'telegram_token':token,'telegram_chat_id':str(chat['id'])}); return {'ok':True,'chat_id':chat['id'],'chat':chat}
@app.post('/api/telegram/test')
async def tg_test(payload:dict):
    token=str(payload.get('token') or settings.telegram_token); chat=str(payload.get('chat_id') or settings.telegram_chat_id)
    await send(token,chat,'✅ Surebet Alert działa. Test Telegram zakończony powodzeniem.')
    return {'ok':True}

def urls():
    host=socket.gethostname(); ips=[]
    try:
        for info in socket.getaddrinfo(host,None):
            ip=info[4][0]
            if ip and ':' not in ip and not ip.startswith('127.'): ips.append(ip)
    except Exception:pass
    ips=list(dict.fromkeys(ips))
    return {'pc':f'http://127.0.0.1:{settings.port}','phone':[f'http://{ip}:{settings.port}' for ip in ips]}

if __name__=='__main__':
    import uvicorn; uvicorn.run('app.main:app',host=settings.host,port=settings.port)
