from __future__ import annotations
import math,time,re
from .models import Surebet,ArbLeg,Quote

# payout factor: 1.0 means stake is fully counted toward gross payout;
# 0.88 means 12% stake tax is deducted from the amount placed at that bookmaker.
def effective_odds(q:Quote, payout_factor:float)->float:
    return q.odds*payout_factor

def allocation(quotes:list[Quote], bankroll:float, factors:dict[str,float]):
    if not quotes or bankroll <= 0 or any(q.odds<=1.0 for q in quotes): return None
    denom=sum(1.0/effective_odds(q,factors.get(q.bookmaker,0.88)) for q in quotes)
    if denom>=1.0: return None
    payout=bankroll/denom
    legs=[]
    for q in quotes:
        eo=effective_odds(q,factors.get(q.bookmaker,0.88))
        stake=payout/eo
        legs.append(ArbLeg(q.selection,q.bookmaker,q.odds,round(stake,2),round(payout,2),q.source_url,q.bookmaker_url))
    rounded_total=round(sum(x.stake for x in legs),2)
    diff=round(bankroll-rounded_total,2)
    if legs: legs[-1].stake=round(legs[-1].stake+diff,2)
    payout_after=[]
    for leg,q in zip(legs,quotes):
        eo=effective_odds(q,factors.get(q.bookmaker,0.88))
        payout_after.append(round(leg.stake*eo,2))
    payout_min=min(payout_after)
    profit=round(payout_min-bankroll,2)
    return denom,round(payout_min,2),profit,legs

def normalize_name(s:str)->str:
    s=re.sub(r'\s+',' ',(s or '').strip().lower())
    return s.replace('–','-').replace('—','-')

def detect(event:str,sport:str,market:str,quotes_by_selection:dict[str,list[Quote]],bankroll:float,factors:dict[str,float],min_profit_pct:float=0.0,max_age:int=180):
    now=time.time(); best={}
    for sel,qs in quotes_by_selection.items():
        fresh=[q for q in qs if now-q.observed_at<=max_age]
        if fresh:
            fresh.sort(key=lambda q:q.odds,reverse=True)
            best[sel]=fresh[0]
    if not best:return []
    keys=list(best); nm={normalize_name(k):k for k in keys}; groups=[]
    m=normalize_name(market)
    if m in {'1x2','1 x 2','wynik','match result','result'} or set(nm)&{'1','x','2'}:
        if all(x in nm for x in ('1','x','2')): groups.append([nm['1'],nm['x'],nm['2']])
    if len(keys)==2:
        groups.append(keys)
    if ('over' in m and 'under' in m) or m in {'u/o','over/under','bts','both teams to score'}:
        if len(keys)==2:groups.append(keys)
    out=[]; seen=set()
    for group in groups:
        q=[best[x] for x in group]; r=allocation(q,bankroll,factors)
        if not r:continue
        denom,payout,profit,legs=r; pct=profit/bankroll*100 if bankroll else 0
        if pct+1e-9>=min_profit_pct:
            arb=Surebet(event,sport,market,round(pct,3),bankroll,payout,profit,legs,now)
            if arb.key() not in seen:out.append(arb);seen.add(arb.key())
    return out
