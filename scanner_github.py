from __future__ import annotations
import asyncio, json, os, time
from pathlib import Path
from app.config import settings, ROOT
from app.models import Quote
from app.surebet import detect
from app.providers.dobrybuk import DobryBukProvider
from app.state import State
from app.telegram import send, render

# GitHub worker: one complete scan, confirmation pass, Telegram alerts and static dashboard data.
# Secrets are read only from environment variables and are never written to the repository.

async def run():
    provider=DobryBukProvider(settings)
    state=State(ROOT/'data'/'github_state.json')
    start=time.time(); errors=[]; events=[]; found=[]; confirmed=[]
    try:
        await provider.start()
        events,errors=await provider.scan_all(settings.sports)
        def convert(ev):
            qdict={}
            for sel,items in ev['quotes'].items():
                for x in items:
                    if x.get('bookmaker')=='Unknown': continue
                    qdict.setdefault(sel,[]).append(Quote(x['selection'],x['odds'],x['bookmaker'],x['observed_at'],x['source_url'],x.get('bookmaker_url','')))
            return detect(ev['event'],ev['sport'],ev['market'],qdict,settings.bankroll,bookmaker_factors(),settings.min_profit_pct,settings.max_quote_age_seconds)
        for ev in events: found.extend(convert(ev))
        found=dedupe_surebets(found)
        found.sort(key=lambda a:a.profit_pct,reverse=True)
        if found:
            await asyncio.sleep(max(1,min(3,int(settings.recheck_delay_seconds))))
            confirm_events,confirm_errors=await provider.scan_all(settings.sports)
            errors += [f'Potwierdzenie: {e}' for e in confirm_errors]
            confirm=[]
            for ev in confirm_events: confirm.extend(convert(ev))
            cmap={a.key():a for a in confirm}
            confirmed=dedupe_surebets([cmap[a.key()] for a in found if a.key() in cmap])
        for arb in confirmed:
            if os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID'):
                if await state.should_alert(arb.key(),arb.profit_pct,settings.dedupe_minutes):
                    await send(os.environ['TELEGRAM_BOT_TOKEN'],os.environ['TELEGRAM_CHAT_ID'],render(arb))
        state.latest=confirmed[:100]; state.last_scan=time.time(); state.stats={
            'events':len(events),'candidates':len(found),'surebets':len(confirmed),
            'elapsed_seconds':round(time.time()-start,2),'interval_seconds':300}
        state.errors=errors
        out=ROOT/'docs'/'data'/'latest.json'; out.parent.mkdir(parents=True,exist_ok=True)
        payload={'generated_at':time.time(),'last_scan':state.last_scan,'latest':[a.to_dict() for a in state.latest], 'stats':state.stats,'errors':state.errors[-10:],'source':'DobryBuk public comparison'}
        out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        await provider.stop()


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

def bookmaker_factors():
    factors={
      'Betclic':1.0,'Fortuna':1.0,'eFortuna':1.0,'Superbet':0.88,'STS':0.88,
      'Forbet':0.88,'LVBet':0.88,'ETOTO':0.88,'eToto':0.88,'Betfan':0.88,
      'Fuksiarz':0.88,'TotalBet':0.88,'Total Bet':0.88,'Betters':0.88,
      'LeBull':0.88,'AdmiralBet':0.88,'BetSport':0.88,'Betsport':0.88,
      'ComeOn':0.88,'PZBuk':0.88,
    }
    factors.update(settings.bookmaker_payout_factors or {})
    return factors

if __name__=='__main__': asyncio.run(run())
