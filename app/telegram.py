from __future__ import annotations
import html
import httpx

def render(arb):
    lines=[f'<b>🚨 SUREBET +{arb.profit_pct:.2f}%</b>',f'{html.escape(arb.sport)} • {html.escape(arb.market)}',f'📌 <b>{html.escape(arb.event)}</b>','',f'💰 Stawka: <b>{arb.bankroll:.2f} zł</b>',f'💵 Wypłata min.: <b>{arb.guaranteed_payout:.2f} zł</b>',f'📈 Zysk min.: <b>+{arb.guaranteed_profit:.2f} zł</b>','']
    for leg in arb.legs:
        bookmaker=html.escape(leg.bookmaker)
        if leg.bookmaker_url:
            bookmaker=f'<a href="{html.escape(leg.bookmaker_url, quote=True)}">{bookmaker}</a>'
        lines.append(f'• {bookmaker}: {html.escape(leg.selection)} @ <b>{leg.odds:.2f}</b> → {leg.stake:.2f} zł')
    lines += ['', '⚠️ Sprawdź kursy bezpośrednio przed zawarciem obu zakładów.']
    return '\n'.join(lines)

async def send(token,chat,text):
    async with httpx.AsyncClient(timeout=15) as c:
        r=await c.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':chat,'text':text,'parse_mode':'HTML','disable_web_page_preview':True})
        if r.status_code>=400: raise RuntimeError(r.text[:500])

async def discover(token):
    async with httpx.AsyncClient(timeout=10) as c:
        r=await c.get(f'https://api.telegram.org/bot{token}/getUpdates')
        r.raise_for_status(); data=r.json()
    chats=[]
    for u in data.get('result',[]):
        msg=u.get('message') or u.get('channel_post')
        if msg and msg.get('chat'): chats.append(msg['chat'])
    return chats[-1] if chats else None
