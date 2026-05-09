// stock_monitor.js — v4
// Prices via Yahoo Finance proxy (no TradingView embed on cards)

const BASE = '/stock_monitor';

const RESEARCH_FIELDS = [
  { key: 'news',            label: 'News',               type: 'text' },
  { key: 'gpa_ratio',       label: 'GPA Ratio (%)',      type: 'percent' },
  { key: 'pe_ratio',        label: 'P/E Ratio',          type: 'number' },
  { key: 'debt_ratio',      label: 'Debt Ratio',         type: 'number' },
  { key: 'ta_situation',    label: 'TA Situation',       type: 'text' },
  { key: 'mgmt_sentiment',  label: 'Last Mgmt Sent.',    type: 'text' },
  { key: 'earnings',        label: 'Earning Transcript', type: 'text' },
  { key: 'conclusion',      label: 'Conclusion',         type: 'text' },
  { key: 'latest_comments', label: 'Latest Comments',   type: 'text' },
];

const PRIORITY = {
  green:  { emoji: '🟢', color: '#3FB950', bg: 'rgba(63,185,80,0.12)',  border: 'rgba(63,185,80,0.3)',  label: 'Info' },
  yellow: { emoji: '🟡', color: '#D29922', bg: 'rgba(210,153,34,0.12)', border: 'rgba(210,153,34,0.3)', label: 'Medium' },
  red:    { emoji: '🔴', color: '#F85149', bg: 'rgba(248,81,73,0.12)',  border: 'rgba(248,81,73,0.3)',  label: 'High' },
};

// ── State ──
let portfolios   = [];
let activePortId = null;
let activeTab    = 'monitor';
let activeTopic  = null;
let assets       = [];
let topics       = [];
let researchRows = [];
let tvWidget     = null;
let activeAsset  = null;

// ══════════════════════════════════════════════════
//  API
// ══════════════════════════════════════════════════
async function api(method, path, body = null) {
  const opts = { method };
  if (body instanceof FormData) opts.body = body;
  else if (body) { opts.headers = {'Content-Type':'application/json'}; opts.body = JSON.stringify(body); }
  const res = await fetch(BASE + path, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
function fd(obj) {
  const f = new FormData();
  Object.entries(obj).forEach(([k,v]) => { if (v !== null && v !== undefined) f.append(k, String(v)); });
  return f;
}

// ══════════════════════════════════════════════════
//  PRICE FETCHER (Yahoo Finance via backend proxy)
// ══════════════════════════════════════════════════
async function fetchPrice(symbol) {
  try {
    const res = await fetch(`${BASE}/price?symbol=${encodeURIComponent(symbol)}`);
    if (!res.ok) return null;
    return await res.json();
  } catch { return null; }
}

function updatePriceCard(symbol, data) {
  const priceEl  = document.getElementById(`price-${symbol}`);
  const changeEl = document.getElementById(`change-${symbol}`);
  const nameEl   = document.getElementById(`name-${symbol}`);
  if (!priceEl) return;

  if (!data || data.price == null) {
    priceEl.innerHTML    = '—';
    if (changeEl) { changeEl.textContent = '—'; changeEl.className = 'sm-asset-change flat'; }
    return;
  }

  const price  = Number(data.price).toFixed(2);
  const chg    = data.change     != null ? Number(data.change).toFixed(2)     : null;
  const chgPct = data.change_pct != null ? Number(data.change_pct).toFixed(2) : null;
  const isPos  = chg != null && parseFloat(chg) >= 0;

  priceEl.innerHTML = `$${price}`;

  if (changeEl && chg !== null && chgPct !== null) {
    const sign = isPos ? '+' : '';
    changeEl.textContent = `${sign}${chg}  (${sign}${chgPct}%)`;
    changeEl.className   = `sm-asset-change ${isPos ? 'pos' : 'neg'}`;
  } else if (changeEl) {
    changeEl.textContent = '—';
    changeEl.className   = 'sm-asset-change flat';
  }

  if (nameEl && data.name) {
    nameEl.textContent = data.name.length > 24 ? data.name.slice(0,24) + '…' : data.name;
  }
}

async function loadAllPrices(symbols) {
  // Fetch up to 5 in parallel at a time
  for (let i = 0; i < symbols.length; i += 5) {
    const chunk = symbols.slice(i, i + 5);
    await Promise.all(chunk.map(async symbol => {
      const data = await fetchPrice(symbol);
      updatePriceCard(symbol, data);
    }));
  }
}

// ══════════════════════════════════════════════════
//  BOOT
// ══════════════════════════════════════════════════
async function init() {
  wireStaticEvents();
  await loadPortfolios();
}

// ══════════════════════════════════════════════════
//  PORTFOLIOS
// ══════════════════════════════════════════════════
async function loadPortfolios() {
  try {
    portfolios = await api('GET', '/portfolios');
    renderSidebar();
    if (portfolios.length > 0) {
      const target = activePortId && portfolios.find(p => p.id === activePortId)
        ? activePortId : portfolios[0].id;
      await selectPortfolio(target);
    } else { showEmptyState(true); }
  } catch(e) { showError('Could not load portfolios: ' + e.message); }
}

async function selectPortfolio(id) {
  activePortId = id; activeTopic = null; activeTab = 'monitor'; activeAsset = null;
  renderSidebar(); showEmptyState(false);
  const p = portfolios.find(x => x.id === id);
  document.getElementById('portfolioTitle').textContent = p ? p.name : '';
  hideChart(); await switchTab('monitor');
}

function renderSidebar() {
  const list = document.getElementById('portfolioList');
  list.innerHTML = '';
  portfolios.forEach(p => {
    const div = document.createElement('div');
    div.className = 'sm-portfolio-item' + (p.id === activePortId ? ' active' : '');
    div.innerHTML = `<div class="sm-portfolio-item-dot"></div>
      <div class="sm-portfolio-item-name" title="${esc(p.name)}">${esc(p.name)}</div>`;
    div.addEventListener('click', () => selectPortfolio(p.id));
    list.appendChild(div);
  });
}

let editingPortId = null;
function openPortfolioModal(editId = null) {
  editingPortId = editId;
  const p = editId ? portfolios.find(x => x.id === editId) : null;
  document.getElementById('portfolioModalTitle').textContent = p ? 'Edit Portfolio' : 'New Portfolio';
  document.getElementById('portfolioNameInput').value = p ? p.name : '';
  document.getElementById('portfolioDescInput').value = p ? (p.description || '') : '';
  document.getElementById('portfolioModal').classList.remove('sm-hidden');
  setTimeout(() => document.getElementById('portfolioNameInput').focus(), 80);
}

async function savePortfolio() {
  const name = document.getElementById('portfolioNameInput').value.trim();
  const desc = document.getElementById('portfolioDescInput').value.trim();
  if (!name) { document.getElementById('portfolioNameInput').focus(); return; }
  try {
    if (editingPortId) {
      await api('PUT', `/portfolios/${editingPortId}`, fd({name, description: desc}));
      closeModal('portfolioModal'); await loadPortfolios();
      document.getElementById('portfolioTitle').textContent = name;
    } else {
      const res = await api('POST', '/portfolios', fd({name, description: desc}));
      closeModal('portfolioModal'); await loadPortfolios();
      if (res.portfolio) await selectPortfolio(res.portfolio.id);
    }
  } catch(e) { showError(e.message); }
}

async function deletePortfolio() {
  const p = portfolios.find(x => x.id === activePortId);
  if (!p || !confirm(`Delete portfolio "${p.name}"?`)) return;
  try { await api('DELETE', `/portfolios/${activePortId}`); activePortId = null; await loadPortfolios(); }
  catch(e) { showError(e.message); }
}

function showEmptyState(show) {
  document.getElementById('emptyState').classList.toggle('sm-hidden', !show);
  document.getElementById('portfolioView').classList.toggle('sm-hidden', show);
}

// ══════════════════════════════════════════════════
//  TABS
// ══════════════════════════════════════════════════
async function switchTab(tab) {
  activeTab = tab;
  ['monitor','research','emails'].forEach(t => {
    const T = t.charAt(0).toUpperCase() + t.slice(1);
    document.getElementById('tab'+T)?.classList.toggle('sm-tab-active', t === tab);
    document.getElementById('tabContent'+T)?.classList.toggle('sm-hidden', t !== tab);
  });
  if (tab === 'monitor')  await loadAndRenderMonitor();
  if (tab === 'research') await loadAndRenderResearch();
  if (tab === 'emails')   await loadAndRenderEmails();
}

// ══════════════════════════════════════════════════
//  MONITOR TAB
// ══════════════════════════════════════════════════
async function loadAndRenderMonitor() {
  try { assets = await api('GET', `/portfolios/${activePortId}/assets`); renderMonitor(); }
  catch(e) { showError(e.message); }
}

function renderMonitor() {
  const grid = document.getElementById('assetsGrid');
  grid.innerHTML = '';

  // Quick-add row
  const addRow = document.createElement('div');
  addRow.style.cssText = 'grid-column:1/-1;';
  addRow.className = 'sm-add-asset-row';
  addRow.innerHTML = `
    <input type="text" class="sm-input" id="quickAddInput"
           placeholder="Add symbols: AAPL, NVDA, TSLA…" style="flex:1;min-width:0;">
    <button class="sm-btn sm-btn-primary" id="quickAddBtn">+ Add</button>
    <label class="sm-btn sm-btn-ghost" style="cursor:pointer;">
      📁 CSV <input type="file" accept=".csv" id="csvMonitorInput" style="display:none;">
    </label>`;
  grid.appendChild(addRow);
  document.getElementById('quickAddBtn').addEventListener('click', quickAddAssets);
  document.getElementById('quickAddInput').addEventListener('keydown', e => { if (e.key==='Enter') quickAddAssets(); });
  document.getElementById('csvMonitorInput').addEventListener('change', handleCsvUpload);

  if (assets.length === 0) {
    const empty = document.createElement('div');
    empty.style.cssText = 'grid-column:1/-1;text-align:center;padding:48px;color:#484F58;font-size:13px;';
    empty.textContent = 'No assets yet — add symbols above to start monitoring.';
    grid.appendChild(empty); hideChart(); return;
  }

  assets.forEach((asset, idx) => {
    const card = document.createElement('div');
    card.className = 'sm-asset-card';
    card.style.animationDelay = `${idx * 0.04}s`;
    card.dataset.symbol = asset.symbol;

    card.innerHTML = `
      <button class="sm-asset-remove" title="Remove">×</button>
      <div class="sm-asset-symbol">${esc(asset.symbol)}</div>
      <div id="name-${asset.symbol}" class="sm-asset-name">&nbsp;</div>
      <div class="sm-asset-price-block">
        <div id="price-${asset.symbol}" class="sm-asset-price">
          <div class="sm-price-loading"></div>
        </div>
        <div id="change-${asset.symbol}" class="sm-asset-change flat">&nbsp;</div>
      </div>
    `;

    card.addEventListener('click', e => {
      if (e.target.classList.contains('sm-asset-remove')) return;
      selectAsset(asset, card);
    });
    card.querySelector('.sm-asset-remove').addEventListener('click', async e => {
      e.stopPropagation(); await removeAsset(asset.symbol);
    });
    grid.appendChild(card);
  });

  // Fetch prices for all assets after cards are rendered
  loadAllPrices(assets.map(a => a.symbol));
}

function selectAsset(asset, card) {
  document.querySelectorAll('.sm-asset-card').forEach(c => c.classList.remove('selected'));
  card.classList.add('selected');
  activeAsset = asset;
  showChart(asset.symbol);
  loadNotesAndComments(asset);
}

async function quickAddAssets() {
  const input = document.getElementById('quickAddInput'); if (!input) return;
  const syms = input.value.split(/[\s,;]+/).map(s => s.trim().toUpperCase()).filter(Boolean);
  if (!syms.length) return;
  input.value = ''; await doAddAssets(syms.join('\n'));
}

async function handleCsvUpload(e) {
  const file = e.target.files[0]; if (!file) return;
  const formData = new FormData(); formData.append('csv_file', file);
  try {
    const res = await fetch(`${BASE}/portfolios/${activePortId}/assets`, {method:'POST',body:formData});
    const data = await res.json();
    if (data.status === 'ok') await loadAndRenderMonitor(); else showError(data.message);
  } catch(e) { showError(e.message); }
  e.target.value = '';
}

async function doAddAssets(symbolsText) {
  try { await api('POST', `/portfolios/${activePortId}/assets`, fd({symbols:symbolsText})); await loadAndRenderMonitor(); }
  catch(e) { showError(e.message); }
}

async function removeAsset(symbol) {
  try { await api('DELETE', `/portfolios/${activePortId}/assets/${symbol}`); await loadAndRenderMonitor(); hideChart(); }
  catch(e) { showError(e.message); }
}

async function saveAssetsFromModal() {
  const text = document.getElementById('assetSymbolsInput').value.trim();
  const csvFile = document.getElementById('assetCsvInput').files[0];
  if (!text && !csvFile) return;
  closeModal('assetModal');
  if (csvFile) {
    const formData = new FormData();
    if (text) formData.append('symbols', text);
    formData.append('csv_file', csvFile);
    try { await fetch(`${BASE}/portfolios/${activePortId}/assets`, {method:'POST',body:formData}); }
    catch(e) { showError(e.message); }
  } else { await doAddAssets(text); }
  await loadAndRenderMonitor();
}

// ── Chart ──
function showChart(symbol) {
  document.getElementById('chartPanel').classList.remove('sm-hidden');
  document.getElementById('chartSymbol').textContent = symbol;
  renderTVChart(symbol);
}
function hideChart() {
  document.getElementById('chartPanel').classList.add('sm-hidden');
  ['commentsSection','notesSection'].forEach(id => document.getElementById(id)?.remove());
}
function renderTVChart(symbol) {
  const container = document.getElementById('tvChartContainer');
  container.innerHTML = '';
  if (typeof TradingView === 'undefined') {
    container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;
      height:100%;color:#484F58;font-family:'IBM Plex Mono',monospace;font-size:13px;">
      TradingView not available</div>`;
    return;
  }
  tvWidget = new TradingView.widget({
    symbol, interval:'D', timezone:'Etc/UTC', theme:'dark', style:'1', locale:'en',
    toolbar_bg:'#0D1117', enable_publishing:false, allow_symbol_change:true,
    container_id:'tvChartContainer', autosize:true, hide_side_toolbar:false,
    studies:['RSI@tv-basicstudies','MACD@tv-basicstudies'],
    backgroundColor:'#0D1117', withdateranges:true, save_image:false,
  });
}

// ══════════════════════════════════════════════════
//  NOTES + COMMENTS (below chart)
// ══════════════════════════════════════════════════
async function loadNotesAndComments(asset) {
  try {
    const [notes, comments] = await Promise.all([
      api('GET', `/portfolios/${activePortId}/assets/${asset.symbol}/notes`),
      api('GET', `/portfolios/${activePortId}/assets/${asset.symbol}/comments`),
    ]);
    renderNotesSection(asset, notes);
    renderCommentsSection(asset, comments);
  } catch(e) { showError(e.message); }
}

/* ── RICH-TEXT NOTE HELPERS ───────────────────────────────────────────
   The note input is a contenteditable div, so pasted content keeps its
   formatting (bold, italics, lists, links, line breaks). Anything that
   gets pasted or saved goes through sanitizeNoteHtml: strips <script>,
   inline event handlers, javascript: URLs and any tag not in the
   whitelist below — keeps the formatting tags.                        */
const NOTE_ALLOWED_TAGS = new Set([
  'P','BR','STRONG','B','EM','I','U','S','STRIKE',
  'UL','OL','LI','A','H1','H2','H3','H4','H5','H6',
  'BLOCKQUOTE','CODE','PRE','SPAN','DIV'
]);
const NOTE_ALLOWED_ATTRS = { 'A': new Set(['href','title','target','rel']) };
const NOTE_REMOVE_TAGS = new Set([
  'SCRIPT','STYLE','IFRAME','OBJECT','EMBED','LINK','META','HEAD','BASE',
  'FORM','INPUT','BUTTON','SELECT','OPTION','TEXTAREA'
]);

function sanitizeNoteHtml(html) {
  const tmp = document.createElement('div');
  tmp.innerHTML = String(html == null ? '' : html);
  const walker = document.createTreeWalker(tmp, NodeFilter.SHOW_ELEMENT);
  const toRemove = [], toUnwrap = [];
  let node;
  while ((node = walker.nextNode())) {
    const tag = node.tagName;
    if (NOTE_REMOVE_TAGS.has(tag)) {
      toRemove.push(node);
    } else if (!NOTE_ALLOWED_TAGS.has(tag)) {
      toUnwrap.push(node);
    } else {
      const allowed = NOTE_ALLOWED_ATTRS[tag] || new Set();
      [...node.attributes].forEach(a => {
        const n = a.name.toLowerCase();
        if (n.startsWith('on') || !allowed.has(n)) node.removeAttribute(a.name);
      });
      if (tag === 'A' && node.hasAttribute('href')) {
        const href = (node.getAttribute('href') || '').trim();
        if (/^(javascript|data|vbscript):/i.test(href)) {
          node.removeAttribute('href');
        } else {
          node.setAttribute('target', '_blank');
          node.setAttribute('rel', 'noopener noreferrer');
        }
      }
    }
  }
  toRemove.forEach(n => n.parentNode && n.parentNode.removeChild(n));
  toUnwrap.forEach(n => {
    if (!n.parentNode) return;
    while (n.firstChild) n.parentNode.insertBefore(n.firstChild, n);
    n.parentNode.removeChild(n);
  });
  return tmp.innerHTML;
}

function looksLikeNoteHtml(s) {
  return /<(p|br|strong|b|em|i|u|s|strike|ul|ol|li|a|h[1-6]|blockquote|code|pre|span|div)\b/i
    .test(String(s || ''));
}

// Render a saved note: HTML if it looks formatted, otherwise plain text
// with line breaks (this also fixes legacy notes whose \n collapsed in
// the previous renderer).
function noteContentHtml(s) {
  if (s == null) return '';
  if (looksLikeNoteHtml(s)) return sanitizeNoteHtml(s);
  return esc(s).replace(/\r\n|\r|\n/g, '<br>');
}

function handleRichPaste(e) {
  e.preventDefault();
  const cd = e.clipboardData || window.clipboardData;
  if (!cd) return;
  const html = cd.getData('text/html');
  const text = cd.getData('text/plain');
  let toInsert = '';
  if (html && html.trim()) {
    toInsert = sanitizeNoteHtml(html);
  } else if (text) {
    toInsert = esc(text).replace(/\r\n|\r|\n/g, '<br>');
  }
  if (!toInsert) return;
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return;
  const range = sel.getRangeAt(0);
  range.deleteContents();
  const tmp = document.createElement('div');
  tmp.innerHTML = toInsert;
  const frag = document.createDocumentFragment();
  let lastNode = null;
  while (tmp.firstChild) lastNode = frag.appendChild(tmp.firstChild);
  range.insertNode(frag);
  if (lastNode) {
    const r = document.createRange();
    r.setStartAfter(lastNode); r.collapse(true);
    sel.removeAllRanges(); sel.addRange(r);
  }
}

function renderNotesSection(asset, notes) {
  document.getElementById('notesSection')?.remove();
  const section = document.createElement('div');
  section.id = 'notesSection';
  section.style.cssText = 'padding:16px 20px;border-top:1px solid #161B22;';
  section.innerHTML = `
    <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#484F58;
                text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">
      📌 Notes — ${esc(asset.symbol)}
    </div>
    <div id="notesList" style="display:flex;flex-direction:column;gap:8px;margin-bottom:14px;">
      ${notes.length === 0
        ? `<div style="color:#484F58;font-size:12px;font-style:italic;">No notes yet.</div>`
        : notes.map(n => noteHtml(n)).join('')}
    </div>
    <div style="background:#161B22;border:1px solid #21262D;border-radius:10px;padding:14px 16px;">
      <div style="display:flex;gap:8px;margin-bottom:10px;align-items:center;flex-wrap:wrap;">
        <span style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#484F58;
                     text-transform:uppercase;letter-spacing:0.08em;">Priority</span>
        ${['green','yellow','red'].map(p => `
          <button class="sm-priority-btn${p==='green'?' sm-priority-active':''}" data-priority="${p}"
            style="padding:5px 12px;border-radius:20px;cursor:pointer;font-size:12px;
                   transition:all 0.18s;font-family:'IBM Plex Sans',sans-serif;
                   border:1px solid ${PRIORITY[p].border};
                   background:${p==='green'?PRIORITY[p].bg:'transparent'};
                   color:${PRIORITY[p].color};">
            ${PRIORITY[p].emoji} ${PRIORITY[p].label}
          </button>`).join('')}
      </div>
      <div class="sm-textarea sm-rich-input" id="newNoteInput"
           contenteditable="true" role="textbox" aria-multiline="true" spellcheck="true"
           data-placeholder="Write a note about ${esc(asset.symbol)}… (Ctrl+Enter to save)"
           style="min-height:70px;max-height:280px;overflow-y:auto;margin-bottom:10px;"></div>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-size:12px;color:#6E7681;">
          <input type="checkbox" id="notifyCheck" style="accent-color:#1F6FEB;">
          📨 Notify subscribers
        </label>
        <button class="sm-btn sm-btn-primary sm-btn-sm" id="addNoteBtn">+ Add Note</button>
      </div>
    </div>`;

  document.getElementById('chartPanel').appendChild(section);

  let selectedPriority = 'green';
  section.querySelectorAll('.sm-priority-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      selectedPriority = btn.dataset.priority;
      section.querySelectorAll('.sm-priority-btn').forEach(b => {
        const p = b.dataset.priority;
        b.style.background = (p === selectedPriority) ? PRIORITY[p].bg : 'transparent';
      });
    });
  });

  document.getElementById('addNoteBtn').addEventListener('click', () => submitNote(asset, () => selectedPriority));
  const noteInputEl = document.getElementById('newNoteInput');
  noteInputEl.addEventListener('paste', handleRichPaste);
  noteInputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.ctrlKey) {
      e.preventDefault();
      document.getElementById('addNoteBtn').click();
    }
  });
  notes.forEach(n => {
    document.getElementById(`del-note-${n.id}`)?.addEventListener('click', async () => {
      try { await api('DELETE', `/notes/${n.id}`); await loadNotesAndComments(asset); }
      catch(e) { showError(e.message); }
    });
  });
}

async function submitNote(asset, getPriority) {
  const inputEl = document.getElementById('newNoteInput');
  if (!inputEl) return;
  // Reject if there is no actual text content (a contenteditable can hold
  // <br> or empty <p> placeholders that look "non-empty" to innerHTML).
  const plain = (inputEl.innerText || inputEl.textContent || '').trim();
  if (!plain) return;
  const note = sanitizeNoteHtml(inputEl.innerHTML).trim();
  if (!note) return;
  const priority = getPriority();
  const notify = document.getElementById('notifyCheck')?.checked || false;
  try {
    await api('POST', `/portfolios/${activePortId}/assets/${asset.symbol}/notes`,
      fd({ note, priority, notify: String(notify) }));
    inputEl.innerHTML = '';
    await loadNotesAndComments(asset);
  } catch(e) { showError(e.message); }
}

function noteHtml(n) {
  const p = PRIORITY[n.priority] || PRIORITY.green;
  const date = new Date(n.created_at).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
  return `
    <div style="border-left:3px solid ${p.color};background:${p.bg};
                border-radius:0 8px 8px 0;padding:10px 14px;
                display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:5px;">
          <span style="font-size:13px;">${p.emoji}</span>
          <span style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:${p.color};
                       text-transform:uppercase;letter-spacing:0.08em;">${p.label}</span>
          ${n.notify ? `<span style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#484F58;">· notified</span>` : ''}
        </div>
        <div class="sm-note-content" style="font-size:13px;color:#C9D1D9;line-height:1.55;word-break:break-word;">${noteContentHtml(n.note)}</div>
        <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#484F58;margin-top:5px;">${date}</div>
      </div>
      <button id="del-note-${n.id}"
        style="background:none;border:none;color:#484F58;cursor:pointer;font-size:16px;
               padding:0 4px;flex-shrink:0;transition:color 0.15s;"
        onmouseover="this.style.color='#F85149'" onmouseout="this.style.color='#484F58'">×</button>
    </div>`;
}

function renderCommentsSection(asset, comments) {
  document.getElementById('commentsSection')?.remove();
  const section = document.createElement('div');
  section.id = 'commentsSection';
  section.style.cssText = 'padding:16px 20px;border-top:1px solid #161B22;';
  section.innerHTML = `
    <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#484F58;
                text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">
      💬 Comments — ${esc(asset.symbol)}
    </div>
    <div id="commentsList" style="display:flex;flex-direction:column;gap:8px;margin-bottom:14px;">
      ${comments.length === 0
        ? `<div style="color:#484F58;font-size:12px;font-style:italic;">No comments yet.</div>`
        : comments.map(c => commentHtml(c)).join('')}
    </div>
    <div style="display:flex;gap:8px;">
      <input type="text" class="sm-input" id="newCommentInput" placeholder="Add a comment…" style="flex:1;">
      <button class="sm-btn sm-btn-primary sm-btn-sm" id="addCommentBtn">Add</button>
    </div>`;
  document.getElementById('chartPanel').appendChild(section);
  document.getElementById('addCommentBtn').addEventListener('click', () => addComment(asset));
  document.getElementById('newCommentInput').addEventListener('keydown', e => { if (e.key==='Enter') addComment(asset); });
  comments.forEach(c => document.getElementById(`del-c-${c.id}`)?.addEventListener('click', () => deleteComment(c.id, asset)));
}

function commentHtml(c) {
  const date = new Date(c.created_at).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
  return `<div style="background:#161B22;border:1px solid #21262D;border-radius:8px;
    padding:10px 13px;display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
    <div>
      <div style="font-size:13px;color:#C9D1D9;line-height:1.5;">${esc(c.comment)}</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#484F58;margin-top:4px;">${date}</div>
    </div>
    <button id="del-c-${c.id}" style="background:none;border:none;color:#484F58;cursor:pointer;
      font-size:16px;padding:0 4px;transition:color 0.15s;"
      onmouseover="this.style.color='#F85149'" onmouseout="this.style.color='#484F58'">×</button>
  </div>`;
}

async function addComment(asset) {
  const input = document.getElementById('newCommentInput');
  const text = input?.value?.trim(); if (!text) return; input.value = '';
  try {
    await api('POST', `/portfolios/${activePortId}/assets/${asset.symbol}/comments`, fd({comment:text}));
    await loadNotesAndComments(asset);
  } catch(e) { showError(e.message); }
}

async function deleteComment(id, asset) {
  try { await api('DELETE', `/comments/${id}`); await loadNotesAndComments(asset); }
  catch(e) { showError(e.message); }
}

// ══════════════════════════════════════════════════
//  RESEARCH TAB
// ══════════════════════════════════════════════════
async function loadAndRenderResearch() {
  try {
    topics = await api('GET', `/portfolios/${activePortId}/research_topics`);
    if (topics.length > 0 && !activeTopic) activeTopic = topics[0];
    else if (topics.length > 0 && activeTopic)
      activeTopic = topics.find(t => t.id === activeTopic.id) || topics[0];
    else activeTopic = null;
    renderResearchTopicTabs();
    await loadResearchRows();
  } catch(e) { showError(e.message); }
}

function renderResearchTopicTabs() {
  const container = document.getElementById('researchTabs');
  container.innerHTML = '';
  topics.forEach(topic => {
    const btn = document.createElement('button');
    btn.className = 'sm-research-tab' + (activeTopic && topic.id === activeTopic.id ? ' active' : '');
    btn.innerHTML = `${esc(topic.name)} <button class="sm-research-tab-remove" title="Remove">×</button>`;
    btn.addEventListener('click', async e => {
      if (e.target.classList.contains('sm-research-tab-remove')) { await deleteResearchTopic(topic); return; }
      activeTopic = topic; renderResearchTopicTabs(); await loadResearchRows();
    });
    container.appendChild(btn);
  });
}

async function loadResearchRows() {
  const empty = document.getElementById('researchEmpty');
  const wrap  = document.getElementById('researchTableWrap');
  if (!activeTopic) { empty.classList.remove('sm-hidden'); wrap.classList.add('sm-hidden'); return; }
  try {
    researchRows = await api('GET', `/research_topics/${activeTopic.id}/rows`);
    empty.classList.add('sm-hidden'); wrap.classList.remove('sm-hidden');
    renderResearchTable();
  } catch(e) { showError(e.message); }
}

function renderResearchTable() {
  const colWidths = [110, ...RESEARCH_FIELDS.map(f =>
    ['gpa_ratio','pe_ratio','debt_ratio'].includes(f.key) ? 100 : 190)];
  const gridCols = colWidths.map(w => `${w}px`).join(' ');
  const minW = colWidths.reduce((a,b)=>a+b,0) + 'px';

  const header = document.getElementById('researchTableHeader');
  header.style.gridTemplateColumns = gridCols;
  header.style.minWidth = minW;
  header.innerHTML = `<div class="sm-research-th">Symbol</div>
    ${RESEARCH_FIELDS.map(f=>`<div class="sm-research-th">${esc(f.label)}</div>`).join('')}`;

  const body = document.getElementById('researchTableBody');
  body.innerHTML = '';

  // Add-symbol row
  const addRow = document.createElement('div');
  addRow.style.cssText = `display:grid;grid-template-columns:${gridCols};min-width:${minW};border-bottom:1px solid #161B22;background:#080C10;`;
  const addCell = document.createElement('div');
  addCell.style.cssText = 'padding:8px 12px;grid-column:1/-1;';
  addCell.innerHTML = `<div style="display:flex;gap:8px;align-items:center;">
    <input type="text" class="sm-input" id="researchAddSym" placeholder="Add symbol to this topic…" style="width:220px;">
    <button class="sm-btn sm-btn-primary sm-btn-sm" id="researchAddSymBtn">+ Add</button>
  </div>`;
  addRow.appendChild(addCell); body.appendChild(addRow);
  document.getElementById('researchAddSymBtn').addEventListener('click', addSymbolToResearch);
  document.getElementById('researchAddSym').addEventListener('keydown', e => { if (e.key==='Enter') addSymbolToResearch(); });

  if (researchRows.length === 0) {
    const empty = document.createElement('div');
    empty.style.cssText = 'padding:32px;text-align:center;color:#484F58;font-size:13px;';
    empty.textContent = 'No symbols yet.'; body.appendChild(empty); return;
  }

  researchRows.forEach(row => {
    const rowEl = document.createElement('div');
    rowEl.className = 'sm-research-row';
    rowEl.style.gridTemplateColumns = gridCols;
    rowEl.style.minWidth = minW;

    const symCell = document.createElement('div');
    symCell.className = 'sm-research-cell sm-research-cell-symbol';
    symCell.style.cssText = 'font-family:"IBM Plex Mono",monospace;font-weight:600;color:#E6EDF3;display:flex;align-items:center;cursor:default;';
    symCell.innerHTML = `${esc(row.symbol)}
      <button class="sm-remove-asset-research" style="margin-left:auto;background:none;border:none;
        color:#484F58;font-size:14px;cursor:pointer;opacity:0;transition:opacity 0.15s;">×</button>`;
    symCell.querySelector('.sm-remove-asset-research').addEventListener('click', () => deleteResearchRow(row));
    rowEl.appendChild(symCell);

    RESEARCH_FIELDS.forEach(field => {
      const cell = document.createElement('div');
      cell.className = 'sm-research-cell';
      const val = row[field.key];
      const isNum = ['percent','number'].includes(field.type);
      const hasVal = val !== null && val !== undefined && val !== '';
      let displayVal = hasVal ? String(val) : '—';
      if (field.type === 'percent' && hasVal) displayVal = Number(val).toFixed(2) + '%';

      cell.innerHTML = `
        <div style="${hasVal?'color:#C9D1D9;':'color:#484F58;'}${isNum&&hasVal?'color:#58A6FF;font-family:\'IBM Plex Mono\',monospace;':''}
          white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;">${esc(displayVal)}</div>
        <span style="position:absolute;right:8px;opacity:0;color:#484F58;font-size:11px;pointer-events:none;transition:opacity 0.15s;" class="edit-hint">✏</span>`;

      cell.addEventListener('click', () => openCellEditor(row, field));
      cell.addEventListener('mouseenter', () => cell.querySelector('.edit-hint').style.opacity='1');
      cell.addEventListener('mouseleave', () => cell.querySelector('.edit-hint').style.opacity='0');
      rowEl.appendChild(cell);
    });

    rowEl.addEventListener('mouseenter', () => symCell.querySelector('.sm-remove-asset-research').style.opacity='1');
    rowEl.addEventListener('mouseleave', () => symCell.querySelector('.sm-remove-asset-research').style.opacity='0');
    body.appendChild(rowEl);
  });
}

async function addSymbolToResearch() {
  const input = document.getElementById('researchAddSym');
  const symbol = input?.value?.trim()?.toUpperCase(); if (!symbol || !activeTopic) return;
  input.value = '';
  try { await api('POST', `/research_topics/${activeTopic.id}/rows/${symbol}`, fd({})); await loadResearchRows(); }
  catch(e) { showError(e.message); }
}

async function deleteResearchRow(row) {
  if (!confirm(`Remove ${row.symbol}?`)) return;
  try { await api('DELETE', `/research_topics/${activeTopic.id}/rows/${row.symbol}`); await loadResearchRows(); }
  catch(e) { showError(e.message); }
}

let cellCtx = null;
function openCellEditor(row, field) {
  cellCtx = { row, field };
  document.getElementById('researchCellTitle').textContent = `${row.symbol} — ${field.label}`;
  document.getElementById('researchCellLabel').textContent = field.label;
  const inputArea = document.getElementById('researchCellInput');
  const inputNum  = document.getElementById('researchCellNumber');
  if (field.type === 'percent' || field.type === 'number') {
    inputArea.classList.add('sm-hidden'); inputNum.classList.remove('sm-hidden');
    const v = row[field.key]; inputNum.value = v != null ? String(v) : '';
    inputNum.placeholder = field.type === 'percent' ? 'e.g. 35.5 (% added automatically)' : 'e.g. 24.5';
    setTimeout(() => inputNum.focus(), 80);
  } else {
    inputNum.classList.add('sm-hidden'); inputArea.classList.remove('sm-hidden');
    const v = row[field.key]; inputArea.value = v != null ? String(v) : '';
    setTimeout(() => inputArea.focus(), 80);
  }
  document.getElementById('researchCellModal').classList.remove('sm-hidden');
}

async function saveCellEdit() {
  if (!cellCtx || !activeTopic) return;
  const { row, field } = cellCtx;
  const inputArea = document.getElementById('researchCellInput');
  const inputNum  = document.getElementById('researchCellNumber');
  let value = '';
  if (field.type === 'percent' || field.type === 'number') {
    const raw = inputNum.value.trim();
    if (raw !== '') {
      const num = parseFloat(raw.replace('%',''));
      if (isNaN(num)) { inputNum.style.borderColor='#F85149'; return; }
      inputNum.style.borderColor=''; value = String(num);
    }
  } else { value = inputArea.value.trim(); }
  closeModal('researchCellModal'); cellCtx = null;
  try {
    await api('POST', `/research_topics/${activeTopic.id}/rows/${row.symbol}`,
      fd({ [field.key]: value, edited_field: field.key }));
    await loadResearchRows();
  } catch(e) { showError(e.message); }
}

async function createResearchTopic() {
  const name = document.getElementById('researchTopicInput').value.trim();
  if (!name) { document.getElementById('researchTopicInput').focus(); return; }
  try {
    const res = await api('POST', `/portfolios/${activePortId}/research_topics`, fd({name}));
    closeModal('researchTopicModal'); activeTopic = res.topic; await loadAndRenderResearch();
  } catch(e) { showError(e.message); }
}

async function deleteResearchTopic(topic) {
  if (!confirm(`Delete topic "${topic.name}" and all data?`)) return;
  try {
    await api('DELETE', `/research_topics/${topic.id}`);
    if (activeTopic && activeTopic.id === topic.id) activeTopic = null;
    await loadAndRenderResearch();
  } catch(e) { showError(e.message); }
}

// ══════════════════════════════════════════════════
//  EMAILS TAB
// ══════════════════════════════════════════════════
async function loadAndRenderEmails() {
  try { const emails = await api('GET', `/portfolios/${activePortId}/emails`); renderEmails(emails); }
  catch(e) { showError(e.message); }
}

function renderEmails(emails) {
  const container = document.getElementById('tabContentEmails');
  container.innerHTML = `
    <div style="max-width:560px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#484F58;
                  text-transform:uppercase;letter-spacing:0.12em;margin-bottom:14px;">📬 Portfolio Subscribers</div>
      <p style="color:#6E7681;font-size:13px;line-height:1.6;margin:0 0 20px;">
        Subscribers are notified automatically when: assets are added/removed,
        research cells are updated, and notes marked "Notify" are posted.
      </p>
      <div id="emailList" style="display:flex;flex-direction:column;gap:8px;margin-bottom:20px;">
        ${emails.length === 0
          ? `<div style="color:#484F58;font-size:13px;font-style:italic;">No subscribers yet.</div>`
          : emails.map(e => emailRowHtml(e)).join('')}
      </div>
      <div style="background:#0D1117;border:1px solid #21262D;border-radius:10px;padding:16px 18px;">
        <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#484F58;
                    text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">Add Subscriber</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <input type="text"  class="sm-input" id="newEmailName" placeholder="Name (optional)" style="width:160px;">
          <input type="email" class="sm-input" id="newEmailAddr" placeholder="email@example.com" style="flex:1;min-width:200px;">
          <button class="sm-btn sm-btn-primary" id="addEmailBtn">+ Add</button>
        </div>
      </div>
      <div style="background:#0D1117;border:1px solid #21262D;border-radius:10px;padding:16px 18px;margin-top:14px;">
        <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#484F58;
                    text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">Send Manual Notification</div>
        <textarea class="sm-textarea" id="manualNotifMsg" placeholder="Type a message to all subscribers…"
                  rows="3" style="min-height:80px;"></textarea>
        <div style="display:flex;justify-content:flex-end;margin-top:10px;">
          <button class="sm-btn sm-btn-primary" id="sendManualNotifBtn">📨 Send to All</button>
        </div>
      </div>
    </div>`;

  document.getElementById('addEmailBtn').addEventListener('click', addSubscriberEmail);
  document.getElementById('newEmailAddr').addEventListener('keydown', e => { if (e.key==='Enter') addSubscriberEmail(); });
  document.getElementById('sendManualNotifBtn').addEventListener('click', sendManualNotification);
  emails.forEach(e => document.getElementById(`del-email-${e.id}`)?.addEventListener('click', () => removeSubscriberEmail(e.id)));
}

function emailRowHtml(e) {
  return `<div style="background:#161B22;border:1px solid #21262D;border-radius:8px;
    padding:10px 14px;display:flex;justify-content:space-between;align-items:center;gap:10px;">
    <div>
      ${e.name ? `<div style="font-size:13px;color:#E6EDF3;margin-bottom:2px;">${esc(e.name)}</div>` : ''}
      <div style="font-family:'IBM Plex Mono',monospace;font-size:12px;color:#58A6FF;">${esc(e.email)}</div>
    </div>
    <button id="del-email-${e.id}" style="background:rgba(248,81,73,0.1);border:1px solid rgba(248,81,73,0.2);
      color:#F85149;border-radius:6px;padding:5px 10px;cursor:pointer;font-size:12px;">Remove</button>
  </div>`;
}

async function addSubscriberEmail() {
  const email = document.getElementById('newEmailAddr')?.value?.trim();
  const name  = document.getElementById('newEmailName')?.value?.trim();
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    document.getElementById('newEmailAddr').style.borderColor='#F85149'; return;
  }
  document.getElementById('newEmailAddr').style.borderColor='';
  try { await api('POST', `/portfolios/${activePortId}/emails`, fd({email, name:name||''})); await loadAndRenderEmails(); }
  catch(e) { showError(e.message); }
}

async function removeSubscriberEmail(emailId) {
  try { await api('DELETE', `/emails/${emailId}`); await loadAndRenderEmails(); }
  catch(e) { showError(e.message); }
}

async function sendManualNotification() {
  const msg = document.getElementById('manualNotifMsg')?.value?.trim();
  if (!msg) { document.getElementById('manualNotifMsg').style.borderColor='#F85149'; return; }
  document.getElementById('manualNotifMsg').style.borderColor='';
  try {
    const res = await api('POST', `/portfolios/${activePortId}/notify`, fd({message:msg}));
    if (res.status === 'ok') {
      showToast(`✓ Sent to ${res.sent_to?.length||0} subscriber(s)`, 'success');
      document.getElementById('manualNotifMsg').value = '';
    } else showError(res.message||'Could not send');
  } catch(e) { showError(e.message); }
}

// ══════════════════════════════════════════════════
//  UTILS
// ══════════════════════════════════════════════════
function esc(str) { const d = document.createElement('div'); d.textContent = String(str??''); return d.innerHTML; }
function closeModal(id) { document.getElementById(id)?.classList.add('sm-hidden'); }
function showError(msg) { showToast('✗ ' + msg, 'error'); }
function showToast(msg, type='error') {
  const cfg = {error:{bg:'#1A0A0A',color:'#F85149'},success:{bg:'#0A1F10',color:'#3FB950'}};
  const c = cfg[type]||cfg.error;
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:24px;right:24px;background:${c.bg};
    border:1px solid ${c.color};border-left:3px solid ${c.color};color:${c.color};
    padding:10px 16px;border-radius:8px;z-index:9999;
    font-family:'IBM Plex Mono',monospace;font-size:12px;max-width:380px;`;
  t.textContent = msg; document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// ══════════════════════════════════════════════════
//  STATIC EVENTS
// ══════════════════════════════════════════════════
function wireStaticEvents() {
  document.getElementById('addPortfolioBtn').addEventListener('click', () => openPortfolioModal());
  document.getElementById('emptyAddPortfolioBtn').addEventListener('click', () => openPortfolioModal());
  document.getElementById('closePortfolioModal').addEventListener('click', () => closeModal('portfolioModal'));
  document.getElementById('cancelPortfolioModal').addEventListener('click', () => closeModal('portfolioModal'));
  document.getElementById('savePortfolioBtn').addEventListener('click', savePortfolio);
  document.getElementById('portfolioNameInput').addEventListener('keydown', e => { if (e.key==='Enter') savePortfolio(); });
  document.getElementById('portfolioModal').addEventListener('click', e => { if (e.target.id==='portfolioModal') closeModal('portfolioModal'); });

  document.getElementById('editPortfolioBtn').addEventListener('click', () => openPortfolioModal(activePortId));
  document.getElementById('deletePortfolioBtn').addEventListener('click', deletePortfolio);
  document.getElementById('addAssetBtn').addEventListener('click', () => {
    document.getElementById('assetSymbolsInput').value = '';
    document.getElementById('assetCsvName').textContent = '';
    document.getElementById('assetModal').classList.remove('sm-hidden');
    setTimeout(() => document.getElementById('assetSymbolsInput').focus(), 80);
  });
  document.getElementById('closeAssetModal').addEventListener('click', () => closeModal('assetModal'));
  document.getElementById('cancelAssetModal').addEventListener('click', () => closeModal('assetModal'));
  document.getElementById('saveAssetsBtn').addEventListener('click', saveAssetsFromModal);
  document.getElementById('assetCsvInput').addEventListener('change', e => {
    document.getElementById('assetCsvName').textContent = e.target.files[0]?.name || '';
  });
  document.getElementById('assetModal').addEventListener('click', e => { if (e.target.id==='assetModal') closeModal('assetModal'); });

  document.getElementById('tabMonitor').addEventListener('click', () => switchTab('monitor'));
  document.getElementById('tabResearch').addEventListener('click', () => switchTab('research'));
  document.getElementById('tabEmails').addEventListener('click', () => switchTab('emails'));
  document.getElementById('closeChartBtn').addEventListener('click', hideChart);

  document.getElementById('addResearchTabBtn').addEventListener('click', () => {
    document.getElementById('researchTopicInput').value = '';
    document.getElementById('researchTopicModal').classList.remove('sm-hidden');
    setTimeout(() => document.getElementById('researchTopicInput').focus(), 80);
  });
  document.getElementById('closeResearchTopicModal').addEventListener('click', () => closeModal('researchTopicModal'));
  document.getElementById('cancelResearchTopic').addEventListener('click', () => closeModal('researchTopicModal'));
  document.getElementById('saveResearchTopic').addEventListener('click', createResearchTopic);
  document.getElementById('researchTopicInput').addEventListener('keydown', e => { if (e.key==='Enter') createResearchTopic(); });
  document.getElementById('researchTopicModal').addEventListener('click', e => { if (e.target.id==='researchTopicModal') closeModal('researchTopicModal'); });

  document.getElementById('closeResearchCellModal').addEventListener('click', () => closeModal('researchCellModal'));
  document.getElementById('cancelResearchCell').addEventListener('click', () => closeModal('researchCellModal'));
  document.getElementById('saveResearchCell').addEventListener('click', saveCellEdit);
  document.getElementById('researchCellModal').addEventListener('click', e => { if (e.target.id==='researchCellModal') closeModal('researchCellModal'); });
  document.getElementById('researchCellNumber').addEventListener('keydown', e => { if (e.key==='Enter') saveCellEdit(); });

  document.addEventListener('keydown', e => {
    if (e.key==='Escape') ['portfolioModal','assetModal','researchCellModal','researchTopicModal'].forEach(id => closeModal(id));
  });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();