from __future__ import annotations
import time,re,html as htmlmod
from typing import Any
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright,Page

SPORTS=['Piłka nożna','Tenis','Koszykówka','Hokej','Piłka ręczna','MMA','Boks','Dart','Żużel','Baseball','Futbol amerykański','Tenis stołowy']
BOOKS={'Superbet','STS','Fortuna','Betclic','Forbet','LVBet','ETOTO','eToto','Betfan','Fuksiarz','TotalBet','Total Bet','Betters','LeBull','AdmiralBet','BetSport','Betsport','ComeOn','PZBuk'}
ODDS_RE=re.compile(r'(?<!\d)(?:[1-9]\d{0,2})(?:[\.,]\d{2})(?!\d)')
TIME_RE=re.compile(r'^\d{1,2}:\d{2}$')

def clean(s):
    s=htmlmod.unescape(s or '')
    s=re.sub(r'\s+',' ',s).strip()
    return s

def cell_data(td):
    txt=clean(td.get_text(' ',strip=True))
    odds=[float(x.replace(',','.')) for x in ODDS_RE.findall(txt)]
    books=[]; urls={}
    for img in td.find_all('img'):
        alt=clean(img.get('alt',''))
        detected=None
        for b in BOOKS:
            if alt.lower()==b.lower() or b.lower() in alt.lower():
                detected=b; books.append(b); break
        if detected:
            a=img.find_parent('a', href=True)
            if a: urls[detected]=a.get('href','')
    for a in td.find_all('a', href=True):
        ah=clean(a.get_text(' ',strip=True))
        href=a.get('href','')
        for b in BOOKS:
            if b.lower() in ah.lower() and b not in books:
                books.append(b); urls[b]=href
    return txt,odds,books,urls

def extract_tables(page_html:str,sport:str,source_url:str):
    soup=BeautifulSoup(page_html,'html.parser'); out=[]; now=time.time()
    for table in soup.find_all('table'):
        rows=table.find_all('tr');
        if not rows:continue
        # Find header row with market columns
        header=[]
        for tr in rows[:3]:
            cells=[clean(x.get_text(' ',strip=True)) for x in tr.find_all(['th','td'])]
            if any(x in {'1','X','2'} for x in cells) or any('1x2' in x.lower() for x in cells): header=cells; break
        if not header:continue
        for tr in rows:
            tds=tr.find_all(['td','th'])
            if len(tds)<4:continue
            cells=[cell_data(td) for td in tds]
            time_text=cells[0][0]
            if not TIME_RE.match(time_text):continue
            event=clean(cells[1][0])
            # remove image alt/team duplication is not critical; require a plausible event label
            if not event or len(event)<5:continue
            market='1X2'
            if len(header)>=4:
                header_tail=[clean(x) for x in header[3:]]
                if header_tail: market=' / '.join(header_tail[:3])
            # parse selection columns from 3rd cell onward, ignoring bonus column where present
            start=3
            row_cells=cells[start:]
            labels=header[start:] if len(header)>start else []
            quotes={}
            for idx,cd in enumerate(row_cells):
                if not cd[1]:continue
                odds=max(cd[1])
                label=labels[idx] if idx<len(labels) else str(idx+1)
                if label.lower() in {'bonusy','bonus',''}: continue
                book=cd[2][0] if cd[2] else 'Unknown'
                if book=='Unknown': continue
                book_url=cd[3].get(book,'') if len(cd)>3 else ''
                if book_url and book_url.startswith('/'):
                    book_url='https://dobrybuk.pl'+book_url
                quotes.setdefault(label,[]).append({'selection':label,'odds':odds,'bookmaker':book,'observed_at':now,'source_url':source_url,'bookmaker_url':book_url})
            if quotes: out.append({'event':event,'sport':sport,'market':market,'quotes':quotes,'observed_at':now,'source_url':source_url})
    return out

class DobryBukProvider:
    def __init__(self,settings): self.settings=settings; self.pw=None; self.browser=None; self.page:Page|None=None
    async def start(self):
        self.pw=await async_playwright().start(); self.browser=await self.pw.chromium.launch(headless=self.settings.headless); self.page=await self.browser.new_page(locale='pl-PL',user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36')
    async def stop(self):
        # Shutdown should never hide the real application error. Playwright can
        # already be disconnected when the console receives Ctrl+C.
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self.pw:
            try:
                await self.pw.stop()
            except Exception:
                pass
    async def _click_sport(self,sport):
        assert self.page
        # Try the most specific control first, then fall back to the text node.
        locators=[
            self.page.get_by_role('button',name=sport,exact=True),
            self.page.get_by_text(sport,exact=True),
        ]
        for loc in locators:
            try:
                count=await loc.count()
                for i in range(count):
                    try:
                        item=loc.nth(i)
                        if await item.is_visible():
                            await item.scroll_into_view_if_needed(timeout=1000)
                            await item.click(timeout=3500)
                            await self.page.wait_for_timeout(250)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

def _event_signature(ev):
    # If a click fails and the source page stays on the same sport, the same
    # table can otherwise be relabelled as every requested sport. Treat an
    # identical event+market+quote matrix as one source event.
    quotes=[]
    for sel,items in sorted((ev.get('quotes') or {}).items()):
        for q in sorted(items,key=lambda x:(str(x.get('bookmaker','')),float(x.get('odds',0)))):
            quotes.append((str(sel).strip().lower(),str(q.get('bookmaker','')).strip().lower(),round(float(q.get('odds',0)),3)))
    return (clean(ev.get('event','')).lower(), clean(ev.get('market','')).lower(), tuple(quotes))

    async def scan_all(self,sports):
        assert self.page
        all_events=[]; errors=[]
        try:
            await self.page.goto(self.settings.source_url,wait_until='domcontentloaded',timeout=45000)
            await self.page.wait_for_timeout(1200)
            # Best effort: dismiss the cookie banner without accepting optional analytics cookies.
            for label in ('Tylko niezbędne','Tylko niezbędne pliki','Akceptuj niezbędne'):
                try:
                    loc=self.page.get_by_text(label,exact=True)
                    if await loc.count() and await loc.first.is_visible():
                        await loc.first.click(timeout=1500); break
                except Exception: pass
        except Exception as e:
            return [], [f'Ładowanie DobryBuk: {e}']
        seen_events=set()
        for sport in sports:
            try:
                clicked=await self._click_sport(sport)
                if not clicked:
                    errors.append(f'{sport}: nie udało się aktywować filtra sportu; pominięto, aby nie duplikować danych')
                    continue
                await self.page.wait_for_timeout(900)
                body=await self.page.content()
                rows=extract_tables(body,sport,self.settings.source_url)
                for row in rows:
                    sig=_event_signature(row)
                    if sig in seen_events:
                        continue
                    seen_events.add(sig)
                    all_events.append(row)
            except Exception as e:
                errors.append(f'{sport}: {e}')
        return all_events,errors
