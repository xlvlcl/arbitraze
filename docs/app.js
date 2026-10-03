const BOOK_META = {
  Betclic:{abbr:'BC', url:'https://www.betclic.pl/'},
  Fortuna:{abbr:'FO', url:'https://www.efortuna.pl/'},
  eFortuna:{abbr:'FO', url:'https://www.efortuna.pl/'},
  Superbet:{abbr:'SB', url:'https://superbet.pl/'},
  STS:{abbr:'STS', url:'https://www.sts.pl/'},
  Forbet:{abbr:'FB', url:'https://www.iforbet.pl/'},
  LVBet:{abbr:'LV', url:'https://lvbet.pl/'},
  ETOTO:{abbr:'ET', url:'https://www.etoto.pl/'},
  eToto:{abbr:'ET', url:'https://www.etoto.pl/'},
  Betfan:{abbr:'BF', url:'https://betfan.pl/'},
  Fuksiarz:{abbr:'FU', url:'https://fuksiarz.pl/'},
  TotalBet:{abbr:'TB', url:'https://totalbet.pl/'},
  'Total Bet':{abbr:'TB', url:'https://totalbet.pl/'},
  Betters:{abbr:'BE', url:'https://betters.pl/'},
  LeBull:{abbr:'LB', url:'https://lebull.pl/'},
  AdmiralBet:{abbr:'AB', url:'https://admiralbet.pl/'},
  BetSport:{abbr:'BS', url:'https://betsport.com.pl/'},
  Betsport:{abbr:'BS', url:'https://betsport.com.pl/'},
  ComeOn:{abbr:'CO', url:'https://www.comeon.com/pl'},
  PZBuk:{abbr:'PZ', url:'https://pzbuk.pl/'}
};

const fmt = (n)=>new Intl.NumberFormat('pl-PL',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(n)||0);
const esc = (s)=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const eur = (n)=>`${fmt(n)} zł`;
function meta(book){return BOOK_META[book]||{abbr:String(book).slice(0,2).toUpperCase(),url:'#'}}
function scaleArb(arb,budget){
  const base=Number(arb.bankroll)||50; const ratio=budget/base;
  const legs=(arb.legs||[]).map(l=>({...l,stake:(Number(l.stake)||0)*ratio,payout:(Number(l.payout)||0)*ratio}));
  let payout=Number(arb.guaranteed_payout||0)*ratio;
  let profit=payout-budget;
  return {legs,payout,profit};
}
function renderLegs(arb,budget){
  const scaled=scaleArb(arb,budget);
  return scaled.legs.map(l=>{
    const m=meta(l.bookmaker); const link=l.bookmaker_url||m.url;
    return `<div class="leg">
      <div class="book"><div class="book-logo">${esc(m.abbr)}</div><div class="book-info"><div class="book-name">${esc(l.bookmaker)}</div><div class="book-sub">Najlepszy dostępny kurs</div></div></div>
      <div class="pick"><div class="pick-label">Wybór</div><div class="pick-value">${esc(l.selection)}</div></div>
      <div class="odds-badge"><div class="odds-stack"><div class="odds">${Number(l.odds).toFixed(2)}</div><div class="stake">→ ${eur(l.stake)}</div></div>${link&&link!=='#'?`<a class="btn btn-small open-btn" href="${esc(link)}" target="_blank" rel="noopener">Otwórz buka ↗</a>`:''}</div>
    </div>`;
  }).join('') || '';
}
function calcHtml(arb,budget){
  const scaled=scaleArb(arb,budget);
  const legMini=scaled.legs.map(l=>`<div class="leg-mini"><span>${esc(l.bookmaker)} · ${esc(l.selection)}</span><strong>${eur(l.stake)}</strong></div>`).join('');
  return `<aside class="calc">
    <div class="calc-title">Twój budżet</div>
    <div class="calc-input"><input aria-label="Budżet" class="budget" data-key="${esc(arb._key)}" type="number" min="1" step="1" value="${fmt(budget).replace(',','.')}"><span>PLN</span></div>
    <div class="calc-grid">
      <div class="calc-stat"><span>Wkład</span><strong>${eur(budget)}</strong></div>
      <div class="calc-stat"><span>Gwarantowana wypłata</span><strong>${eur(scaled.payout)}</strong></div>
      <div class="calc-stat full"><span>Gwarantowany zysk</span><strong style="color:var(--green)">+${eur(scaled.profit)}</strong></div>
    </div>
    <div>${legMini}</div>
    <div class="warning">Kursy mogą zmienić się po wykryciu. Przed zagraniem sprawdź oba kursy bezpośrednio u bukmachera.</div>
  </aside>`;
}
function card(arb,defaultBudget){
  arb._key = arb.event+'|'+arb.market+'|'+arb.sport+'|'+(arb.legs||[]).map(x=>x.bookmaker+'@'+x.selection).sort().join('|');
  const b=scaleArb(arb,defaultBudget);
  const tags = `<div class="arb-line"><span class="sport-tag">${esc(arb.sport)}</span><span class="profit">+${Number(arb.profit_pct||0).toFixed(2)}%</span><span class="market">${esc(arb.market||'Rynek')}</span></div>`;
  return `<article class="arb glass" data-profit="${Number(arb.profit_pct||0)}" data-sport="${esc(arb.sport)}">
    <div class="arb-top"><div class="arb-left">${tags}<h2 class="event">${esc(arb.event)}</h2></div><div class="status-pill"><span class="dot"></span> potwierdzony</div></div>
    <div class="arb-body"><div class="legs">${renderLegs(arb,defaultBudget)}</div>${calcHtml(arb,defaultBudget)}</div>
  </article>`;
}

let lastData={latest:[],stats:{}};
let globalBudget=50;

async function loadLocal(){const r=await fetch('/api/status',{cache:'no-store'}); if(!r.ok)throw new Error('status'); return r.json();}
async function loadStatic(){const r=await fetch('data/latest.json?x='+Date.now(),{cache:'no-store'}); if(!r.ok)throw new Error('data'); return r.json();}
async function getData(){const staticMode=location.pathname.includes('/docs/') || window.SUREBET_STATIC; try{return staticMode?await loadStatic():await loadLocal()}catch(e){if(!staticMode)return loadStatic();throw e}}
function repaint(){
  const list=document.getElementById('list');
  const sport=document.getElementById('sportFilter').value; const min=Number(document.getElementById('minFilter').value)||0;
  let items=(lastData.latest||[]).filter(x=>Number(x.profit_pct||0)>=min && (!sport||x.sport===sport));
  items=items.sort((a,b)=>(Number(b.profit_pct)||0)-(Number(a.profit_pct)||0));
  document.getElementById('count').textContent=items.length;
  document.getElementById('best').textContent=items.length?`+${Number(items[0].profit_pct||0).toFixed(2)}%`:'—';
  list.innerHTML=items.length?items.slice(0,100).map(x=>card({...x},globalBudget)).join(''):`<div class="empty glass"><div class="icon">⌁</div><h3>Brak potwierdzonych surebetów</h3><p>System pokaże okazję tutaj, gdy policzony arbitraż przekroczy Twój próg.</p></div>`;
  document.getElementById('events').textContent=lastData.stats?.events??0;
  const ts=lastData.last_scan || lastData.generated_at; document.getElementById('last').textContent=ts?new Date((Number(ts)||0)*1000).toLocaleString('pl-PL'):'—';
  const errs=lastData.errors||[]; document.getElementById('statusText').textContent=errs.length?'uwaga':'monitoring aktywny';
  if(errs.length){document.getElementById('statusDot').style.background='#fbbf24';}else{document.getElementById('statusDot').style.background='var(--green)';}
  const sports=[...new Set((lastData.latest||[]).map(x=>x.sport).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pl'));
  const sel=document.getElementById('sportFilter'); const current=sel.value; sel.innerHTML='<option value="">Wszystkie sporty</option>'+sports.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join(''); sel.value=sports.includes(current)?current:'';
}
async function load(){try{lastData=await getData(); repaint()}catch(e){document.getElementById('statusText').textContent='brak danych';document.getElementById('statusDot').style.background='#fb7185'}}
async function scanNow(){
  if(window.SUREBET_STATIC)return;
  document.getElementById('statusText').textContent='skanuję…';
  try{await fetch('/api/scan-now',{method:'POST'});}catch(e){}
  await load();
}
document.addEventListener('input',e=>{
  if(e.target.classList.contains('budget')){globalBudget=Math.max(1,Number(e.target.value)||1); const y=window.scrollY; repaint(); window.scrollTo(0,y)}
});
document.getElementById('sportFilter')?.addEventListener('change',repaint);
document.getElementById('minFilter')?.addEventListener('input',repaint);
document.getElementById('globalBudget')?.addEventListener('input',e=>{globalBudget=Math.max(1,Number(e.target.value)||1); const y=window.scrollY; repaint(); window.scrollTo(0,y)});
document.getElementById('scanBtn')?.addEventListener('click',scanNow);
load(); setInterval(load,30000);
