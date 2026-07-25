// stock_monitor.js — v5.4
// Prices via Yahoo Finance proxy (no TradingView embed on cards)

const BASE = '/stock_monitor';

const RESEARCH_FIELDS = [
  { key: 'rating',          label: 'Rating',             type: 'rating' },
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
  green:  { emoji: '🟢', color: '#3FB950', bg: 'rgba(63,185,80,0.12)',  border: 'rgba(63,185,80,0.3)',
            glow: 'rgba(63,185,80,0.22)',  label: 'Positivo' },
  yellow: { emoji: '🟡', color: '#D29922', bg: 'rgba(210,153,34,0.12)', border: 'rgba(210,153,34,0.3)',
            glow: 'rgba(210,153,34,0.22)', label: 'Alerta' },
  red:    { emoji: '🔴', color: '#F85149', bg: 'rgba(248,81,73,0.12)',  border: 'rgba(248,81,73,0.3)',
            glow: 'rgba(248,81,73,0.22)',  label: 'Negativo' },
};

const ALERT_BADGE = {
  above_target: { cls: 'sm-badge-target',  text: '🎯 TAKE PROFIT ALCANZADO' },
  below_stop:   { cls: 'sm-badge-stop',    text: '🛑 STOP LOSS ALCANZADO' },
  in_range:     { cls: 'sm-badge-range',   text: 'En rango' },
  no_price:     { cls: 'sm-badge-noprice', text: 'Sin precio' },
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
let alerts       = [];
let alertsCollapsed = false;
let alertFilter     = '';

// ══════════════════════════════════════════════════
//  API
// ══════════════════════════════════════════════════
async function api(method, path, body = null) {
  const opts = { method };
  if (body instanceof FormData) opts.body = body;
  else if (body) { opts.headers = {'Content-Type':'application/json'}; opts.body = JSON.stringify(body); }
  const res = await fetch(BASE + path, opts);
  if (!res.ok) {
    // El backend manda {status:'error', message:'…'} — mejor eso que un "HTTP 500" pelado
    let detail = '';
    try { const body = await res.json(); detail = body?.message || body?.detail || ''; } catch {}
    throw new Error(detail ? `${detail}` : `HTTP ${res.status}`);
  }
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
  ['monitor','research','alerts','emails'].forEach(t => {
    const T = t.charAt(0).toUpperCase() + t.slice(1);
    document.getElementById('tab'+T)?.classList.toggle('sm-tab-active', t === tab);
    document.getElementById('tabContent'+T)?.classList.toggle('sm-hidden', t !== tab);
  });
  if (tab === 'monitor')  await loadAndRenderMonitor();
  if (tab === 'research') await loadAndRenderResearch();
  if (tab === 'alerts')   await loadAndRenderAlerts();
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
    const removeBtn = card.querySelector('.sm-asset-remove');
    removeBtn.title = `Quitar ${asset.symbol}`;
    removeBtn.addEventListener('click', async e => {
      e.stopPropagation();
      const ok = await smConfirm({
        title: 'Quitar activo',
        text: `¿Quitar ${asset.symbol} del portfolio?`,
        sub: 'Se borran también sus niveles de alarma. Las notas y comentarios quedan guardados.',
        okLabel: 'Quitar activo',
        danger: true,
      });
      if (!ok) return;
      await removeAsset(asset.symbol);
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
    <div class="sm-note-composer">
      <div class="sm-note-priority-row">
        <span class="sm-note-priority-label">Prioridad</span>
        ${['green','yellow','red'].map(p => `
          <button type="button" class="sm-priority-btn" data-priority="${p}"
            style="border:1px solid ${PRIORITY[p].border};background:transparent;
                   color:${PRIORITY[p].color};--sm-prio-glow:${PRIORITY[p].glow};">
            <span>${PRIORITY[p].emoji}</span><span>${PRIORITY[p].label}</span>
          </button>`).join('')}
      </div>
      <div class="sm-textarea sm-rich-input" id="newNoteInput"
           contenteditable="true" role="textbox" aria-multiline="true" spellcheck="true"
           data-placeholder="Escribí una nota sobre ${esc(asset.symbol)}… (Ctrl+Enter para guardar)"
           style="min-height:80px;max-height:280px;overflow-y:auto;margin-bottom:12px;"></div>
      <div class="sm-note-actions">
        <label class="sm-notify-toggle" id="notifyToggle">
          <input type="checkbox" id="notifyCheck">
          <span>📨 Notificar subscribers</span>
        </label>
        <button class="sm-btn sm-btn-primary sm-btn-sm" id="addNoteBtn">+ Add Note</button>
      </div>
      <div class="sm-note-sending sm-hidden" id="noteSending">
        <span class="sm-spinner sm-spinner-dark"></span>
        <span id="noteSendingText">Guardando nota…</span>
      </div>
    </div>`;

  document.getElementById('chartPanel').appendChild(section);

  // ── Selección de prioridad con feedback visual ──
  let selectedPriority = 'green';
  const paintPriority = () => {
    section.querySelectorAll('.sm-priority-btn').forEach(b => {
      const p  = b.dataset.priority;
      const on = (p === selectedPriority);
      b.classList.toggle('sm-priority-active', on);
      b.style.background  = on ? PRIORITY[p].bg : 'transparent';
      b.style.borderColor = on ? PRIORITY[p].color : PRIORITY[p].border;
    });
  };
  section.querySelectorAll('.sm-priority-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      selectedPriority = btn.dataset.priority;
      paintPriority();
      btn.classList.remove('sm-prio-pulse');
      void btn.offsetWidth;                       // reinicia la animación
      btn.classList.add('sm-prio-pulse');
      setTimeout(() => btn.classList.remove('sm-prio-pulse'), 360);
    });
  });
  paintPriority();

  // ── Toggle de notificación ──
  const notifyCheck  = document.getElementById('notifyCheck');
  const notifyToggle = document.getElementById('notifyToggle');
  notifyCheck?.addEventListener('change', () =>
    notifyToggle?.classList.toggle('sm-on', notifyCheck.checked));

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
      const ok = await smConfirm({
        title: 'Borrar nota',
        text: '¿Borrar esta nota?',
        sub: 'La acción no se puede deshacer.',
        okLabel: 'Borrar', danger: true });
      if (!ok) return;
      try { await api('DELETE', `/notes/${n.id}`); await loadNotesAndComments(asset); }
      catch(e) { showError(e.message); }
    });
  });
}

let noteSubmitting = false;
async function submitNote(asset, getPriority) {
  if (noteSubmitting) return;
  const inputEl = document.getElementById('newNoteInput');
  if (!inputEl) return;
  // Rechaza si no hay texto real (un contenteditable puede tener <br> o <p> vacíos)
  const plain = (inputEl.innerText || inputEl.textContent || '').trim();
  if (!plain) { inputEl.focus(); return; }
  const note = sanitizeNoteHtml(inputEl.innerHTML).trim();
  if (!note) return;
  const priority = getPriority();
  const notify = document.getElementById('notifyCheck')?.checked || false;

  const btn     = document.getElementById('addNoteBtn');
  const sending = document.getElementById('noteSending');
  const sendTxt = document.getElementById('noteSendingText');

  noteSubmitting = true;
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="sm-spinner"></span> Enviando…`; }
  if (sendTxt) sendTxt.textContent = notify
    ? 'Guardando nota y notificando subscribers…'
    : 'Guardando nota…';
  sending?.classList.remove('sm-hidden');
  inputEl.setAttribute('contenteditable', 'false');

  try {
    await api('POST', `/portfolios/${activePortId}/assets/${asset.symbol}/notes`,
      fd({ note, priority, notify: String(notify) }));
    inputEl.innerHTML = '';
    showToast(notify ? '✓ Nota guardada y enviada' : '✓ Nota guardada', 'success');
    await loadNotesAndComments(asset);
  } catch(e) {
    showError(e.message);
  } finally {
    noteSubmitting = false;
    // El re-render puede haber reemplazado estos nodos: los buscamos de nuevo
    const b = document.getElementById('addNoteBtn');
    if (b) { b.disabled = false; b.textContent = '+ Add Note'; }
    document.getElementById('noteSending')?.classList.add('sm-hidden');
    document.getElementById('newNoteInput')?.setAttribute('contenteditable', 'true');
  }
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
  const colWidths = [110, ...RESEARCH_FIELDS.map(f => {
    if (f.key === 'rating') return 90;
    if (['gpa_ratio','pe_ratio','debt_ratio'].includes(f.key)) return 100;
    return 190;
  })];
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

      // Special render for the rating column: color pill
      if (field.type === 'rating') {
        if (hasVal) {
          const r = Number(val);
          const cls = ratingClass(r);
          cell.innerHTML = `
            <div class="sm-rating-pill ${cls}">${r.toFixed(1)}</div>
            <span style="position:absolute;right:8px;opacity:0;color:#484F58;font-size:11px;pointer-events:none;transition:opacity 0.15s;" class="edit-hint">✏</span>`;
        } else {
          cell.innerHTML = `
            <div style="color:#484F58;">—</div>
            <span style="position:absolute;right:8px;opacity:0;color:#484F58;font-size:11px;pointer-events:none;transition:opacity 0.15s;" class="edit-hint">✏</span>`;
        }
      } else {
        let displayVal = hasVal ? String(val) : '—';
        if (field.type === 'percent' && hasVal) displayVal = Number(val).toFixed(2) + '%';
        cell.innerHTML = `
          <div style="${hasVal?'color:#C9D1D9;':'color:#484F58;'}${isNum&&hasVal?'color:#58A6FF;font-family:\'IBM Plex Mono\',monospace;':''}
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;">${esc(displayVal)}</div>
          <span style="position:absolute;right:8px;opacity:0;color:#484F58;font-size:11px;pointer-events:none;transition:opacity 0.15s;" class="edit-hint">✏</span>`;
      }

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

// Maps rating 0–5 to a CSS class (gradient red → green)
function ratingClass(r) {
  if (r >= 4.5) return 'r-5';
  if (r >= 4.0) return 'r-4';
  if (r >= 3.0) return 'r-3';
  if (r >= 2.0) return 'r-2';
  return 'r-1';
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
  const isNumeric = (field.type === 'percent' || field.type === 'number' || field.type === 'rating');
  if (isNumeric) {
    inputArea.classList.add('sm-hidden'); inputNum.classList.remove('sm-hidden');
    const v = row[field.key]; inputNum.value = v != null ? String(v) : '';
    if (field.type === 'percent') {
      inputNum.placeholder = 'e.g. 35.5 (% added automatically)';
      inputNum.removeAttribute('min'); inputNum.removeAttribute('max');
    } else if (field.type === 'rating') {
      inputNum.placeholder = '0.0 – 5.0';
      inputNum.min = '0'; inputNum.max = '5'; inputNum.step = '0.1';
    } else {
      inputNum.placeholder = 'e.g. 24.5';
      inputNum.removeAttribute('min'); inputNum.removeAttribute('max');
    }
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
  const isNumeric = (field.type === 'percent' || field.type === 'number' || field.type === 'rating');
  let value = '';
  if (isNumeric) {
    const raw = inputNum.value.trim();
    if (raw !== '') {
      const num = parseFloat(raw.replace('%',''));
      if (isNaN(num)) { inputNum.style.borderColor='#F85149'; return; }
      if (field.type === 'rating' && (num < 0 || num > 5)) {
        inputNum.style.borderColor='#F85149'; return;
      }
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
//  IMPORT FROM EXCEL — uploads .xlsx, lists sheets,
//  asks an LLM to extract canonical research rows.
// ══════════════════════════════════════════════════
let importExcelFile = null;

function openImportExcelModal() {
  if (!activePortId) { showError('Select a portfolio first'); return; }
  importExcelFile = null;
  document.getElementById('importExcelInput').value = '';
  document.getElementById('importExcelName').textContent = '';
  document.getElementById('importExcelSheetsList').innerHTML = '';
  document.getElementById('importExcelSheetsField').classList.add('sm-hidden');
  document.getElementById('importExcelSymbols').value = '';
  document.getElementById('importExcelSymbolsField').classList.add('sm-hidden');
  document.querySelector('input[name="importExcelMode"][value="overwrite"]').checked = true;
  document.getElementById('importExcelStatus').textContent = '';
  document.getElementById('runImportExcel').disabled = true;
  document.getElementById('importExcelModal').classList.remove('sm-hidden');
}

async function onImportExcelFileChosen(e) {
  const f = e.target.files[0];
  if (!f) return;
  importExcelFile = f;
  document.getElementById('importExcelName').textContent = f.name;
  document.getElementById('importExcelStatus').textContent = 'Reading sheets…';
  document.getElementById('runImportExcel').disabled = true;
  try {
    const form = new FormData(); form.append('file', f);
    const res = await api('POST', `/portfolios/${activePortId}/research_topics/list_sheets`, form);
    const list = document.getElementById('importExcelSheetsList');
    list.innerHTML = res.sheets.map((s, i) => `
      <label style="display:flex;align-items:center;gap:8px;padding:4px 6px;cursor:pointer;color:#C9D1D9;font-size:12px;">
        <input type="checkbox" class="import-sheet-cb" value="${esc(s)}" ${i===0?'checked':''}
               style="width:auto;flex:0 0 auto;margin:0;">
        <span>${esc(s)}</span>
      </label>`).join('');
    document.getElementById('importExcelSheetsField').classList.remove('sm-hidden');
    document.getElementById('importExcelStatus').textContent =
      `${res.sheets.length} sheet(s) found. Tick the ones to import.`;
    document.getElementById('runImportExcel').disabled = false;
  } catch(err) {
    document.getElementById('importExcelStatus').innerHTML =
      `<span style="color:#F85149;">⚠ ${esc(err.message)}</span>`;
  }
}

async function runImportExcel() {
  if (!importExcelFile || !activePortId) return;
  const sheets = [...document.querySelectorAll('.import-sheet-cb:checked')].map(cb => cb.value);
  if (sheets.length === 0) {
    document.getElementById('importExcelStatus').innerHTML =
      `<span style="color:#D29922;">Pick at least one sheet.</span>`; return;
  }
  const mode = document.querySelector('input[name="importExcelMode"]:checked').value;
  const symbols = document.getElementById('importExcelSymbols').value.trim();

  const btn = document.getElementById('runImportExcel');
  btn.disabled = true; btn.textContent = 'Importing…';
  document.getElementById('importExcelStatus').textContent =
    `Calling LLM for ${sheets.length} sheet(s)… this can take 30–90s.`;

  const form = new FormData();
  form.append('file', importExcelFile);
  form.append('sheets', sheets.join(','));
  form.append('mode', mode);
  if (symbols) form.append('symbols_filter', symbols);

  try {
    const res = await api('POST', `/portfolios/${activePortId}/research_topics/import_excel`, form);
    const lines = res.summary.map(s => {
      if (s.status === 'error') {
        return `<div style="color:#F85149;margin:2px 0;">⚠ <b>${esc(s.sheet)}</b> — ${esc(s.error || 'failed')}</div>`;
      }
      return `<div style="color:#2ea043;margin:2px 0;">✓ <b>${esc(s.sheet)}</b> → ${s.rows_upserted}/${s.rows_extracted} rows</div>`;
    }).join('');
    document.getElementById('importExcelStatus').innerHTML = lines;
    const hasErrors = res.summary.some(s => s.status === 'error');
    await loadAndRenderResearch();
    // Only auto-close if everything went through cleanly; otherwise leave the
    // modal open so the user can read the per-sheet errors.
    if (!hasErrors) {
      setTimeout(() => closeModal('importExcelModal'), 2200);
    }
  } catch(err) {
    document.getElementById('importExcelStatus').innerHTML =
      `<span style="color:#F85149;">⚠ ${esc(err.message)}</span>`;
  } finally {
    btn.disabled = false; btn.textContent = 'Run Import';
  }
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
//  PRICE ALERTS TAB
//  Targets (se tocan desde abajo) y stop loss (desde arriba).
//  No hay recorrido automático: alguien entra y le da Play.
// ══════════════════════════════════════════════════
async function loadAndRenderAlerts() {
  try {
    const res = await api('GET', `/portfolios/${activePortId}/alerts`);
    // Contrato: { status, alerts: [...], warning: string|null }
    alerts = Array.isArray(res) ? res : (res.alerts || []);
    const warning = Array.isArray(res) ? null : (res.warning || null);
    let events = [];
    try { events = await api('GET', `/portfolios/${activePortId}/alerts/events?top=15`); }
    catch { events = []; }
    renderAlerts(Array.isArray(events) ? events : [], warning);
  } catch(e) {
    renderAlertsError(e.message);
  }
}

function renderAlertsError(msg) {
  const container = document.getElementById('tabContentAlerts');
  container.innerHTML = `
    <div class="sm-alerts-panel">
      <div class="sm-alerts-panel-head">
        <div class="sm-alerts-panel-title">🔔 Price Alerts</div>
        <button class="sm-btn sm-btn-ghost sm-btn-sm" id="retryAlertsBtn">↻ Reintentar</button>
      </div>
      <div class="sm-alerts-panel-body">
        <div class="sm-alerts-warning">
          <span>⚠️</span>
          <div>
            <b>No se pudo cargar el panel de alarmas.</b><br>
            ${esc(msg || 'Error desconocido')}<br><br>
            Si es la primera vez que abrís esta pestaña, falta correr el script
            <code>sql/sm_price_alerts.sql</code> en la base de research
            (crea las tablas <code>sm_asset_alerts</code> / <code>sm_alert_events</code>
            y los stored procedures <code>sm_*_alert*</code>).
          </div>
        </div>
      </div>
    </div>`;
  document.getElementById('retryAlertsBtn')?.addEventListener('click', loadAndRenderAlerts);
  showError(msg);
}

function fmtNum(v, dec = 2) {
  if (v === null || v === undefined || v === '') return '—';
  return Number(v).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function renderAlerts(events, warning) {
  const container = document.getElementById('tabContentAlerts');

  const warnHtml = warning ? `
    <div class="sm-alerts-warning">
      <span>⚠️</span>
      <div>${esc(warning)}<br>
        Corré <code>sql/sm_price_alerts.sql</code> en la base de research y recargá.</div>
    </div>` : '';

  const rowsHtml = alerts.length === 0
    ? `<div style="padding:26px;text-align:center;color:#484F58;font-size:13px;">
         Todavía no hay activos en este portfolio. Agregá símbolos en la pestaña Monitor.
       </div>`
    : alerts.map(a => `
      <div class="sm-alert-row" data-symbol="${esc(a.symbol)}">
        <div class="sm-alert-sym">${esc(a.symbol)}${a.orphan ? ' <span style="color:#D29922;font-size:10px;">(fuera del portfolio)</span>' : ''}</div>
        <div class="sm-alert-last">
          Último visto: ${fmtNum(a.last_price)}
          ${a.last_triggered_at ? ` · disparó ${esc(String(a.last_trigger_type || ''))}` : ''}
        </div>
        <div>
          <input type="text" inputmode="decimal" class="sm-alert-input sm-target"
                 data-field="target" placeholder="Target ↑"
                 value="${a.target_price !== null && a.target_price !== undefined ? a.target_price : ''}">
        </div>
        <div>
          <input type="text" inputmode="decimal" class="sm-alert-input sm-stop"
                 data-field="stop" placeholder="Stop loss ↓"
                 value="${a.stop_loss !== null && a.stop_loss !== undefined ? a.stop_loss : ''}">
        </div>
        <div>
          <label class="sm-notify-toggle${a.enabled ? ' sm-on' : ''}" style="padding:5px 9px;">
            <input type="checkbox" class="sm-alert-enabled" ${a.enabled ? 'checked' : ''}>
            <span>Activa</span>
          </label>
        </div>
        <div class="sm-alert-saved">✓ guardado</div>
      </div>`).join('');

  const eventsHtml = events.length === 0
    ? `<div style="color:#484F58;font-size:12px;font-style:italic;">Todavía no hubo disparos.</div>`
    : events.map(e => `
        <div class="sm-alert-event">
          <span>${e.event_type === 'stop_loss' ? '🛑' : '🎯'}</span>
          <b>${esc(e.symbol)}</b>
          <span>${e.event_type === 'stop_loss' ? 'stop loss' : 'target'} ${fmtNum(e.level_price)}</span>
          <span>· precio ${fmtNum(e.price)}</span>
          ${e.notified ? '<span style="color:#3FB950;">· notificado</span>' : ''}
          <span class="sm-ev-date">${esc(String(e.created_at || '').slice(0, 16))}</span>
        </div>`).join('');

  container.innerHTML = `
    <div class="sm-alerts-layout">

      ${warnHtml}

      <!-- ── Configuración de niveles ── -->
      <div class="sm-alerts-panel">
        <div class="sm-alerts-panel-head">
          <button class="sm-alerts-toggle" id="toggleAlertsCfg" title="Mostrar / ocultar">
            <span class="sm-chevron${alertsCollapsed ? ' sm-collapsed' : ''}">▾</span>
            <span class="sm-alerts-panel-title">⚙️ Niveles por activo</span>
            <span class="sm-alerts-count" id="alertsCount"></span>
          </button>
          <div class="sm-alerts-head-actions">
            <input type="text" class="sm-alert-input sm-alert-filter" id="alertFilterInput"
                   placeholder="🔎 Filtrar por símbolo…" value="${esc(alertFilter)}">
            <button class="sm-btn sm-btn-ghost sm-btn-sm" id="importLevelsBtn"
                    title="Importar niveles desde una planilla">📥 Importar Excel</button>
            <button class="sm-btn sm-btn-ghost sm-btn-sm" id="reloadAlertsBtn">↻ Recargar</button>
          </div>
        </div>
        <div class="sm-alerts-panel-body${alertsCollapsed ? ' sm-hidden' : ''}" id="alertsCfgBody">
          <p class="sm-alerts-hint">
            El <b style="color:#3FB950;">target</b> queda alcanzado cuando el precio
            <b>llega o supera</b> ese valor; el <b style="color:#F85149;">stop loss</b>
            cuando el precio <b>llega o cae por debajo</b>. Dejá el campo vacío para no
            usar ese nivel. Los cambios se guardan al salir del campo.
          </p>
          <div class="sm-alert-table">
            <div class="sm-alert-thead">
              <div>Activo</div><div>Estado</div><div>Target ↑</div>
              <div>Stop loss ↓</div><div>Alarma</div><div></div>
            </div>
            ${rowsHtml}
            <div id="alertsEmptyFilter" class="sm-hidden"
                 style="padding:22px;text-align:center;color:#484F58;font-size:12px;">
              Ningún símbolo coincide con el filtro.
            </div>
          </div>
        </div>
      </div>

      <!-- ── Corrida manual ── -->
      <div class="sm-alerts-panel">
        <div class="sm-alerts-panel-head">
          <div class="sm-alerts-panel-title">▶️ Recorrido de precios</div>
        </div>
        <div class="sm-alerts-panel-body">
          <p class="sm-alerts-hint">
            Recorre todos los activos con niveles cargados, trae el precio actual y arma el
            informe. Se dispara alarma sólo cuando el precio <b>cruza</b> el nivel respecto
            de la última corrida — en la primera corrida se toma la referencia y no dispara nada.
          </p>
          <div class="sm-run-box">
            <button class="sm-btn sm-btn-primary sm-run-btn" id="runAlertsBtn">▶ Correr alarmas</button>
            <label class="sm-notify-toggle sm-on" id="runNotifyToggle">
              <input type="checkbox" id="runAlertsNotify" checked>
              <span>📨 Mandar mails a los subscribers</span>
            </label>
            <div class="sm-run-status" id="runAlertsStatus"></div>
          </div>
          <div id="runAlertsResults"></div>
        </div>
      </div>

      <!-- ── Historial ── -->
      <div class="sm-alerts-panel">
        <div class="sm-alerts-panel-head">
          <div class="sm-alerts-panel-title">🕘 Últimos disparos</div>
        </div>
        <div class="sm-alerts-panel-body">
          <div class="sm-alert-events">${eventsHtml}</div>
        </div>
      </div>

    </div>`;

  // ── Wiring ──
  document.getElementById('reloadAlertsBtn').addEventListener('click', loadAndRenderAlerts);
  document.getElementById('importLevelsBtn').addEventListener('click', openImportLevelsModal);

  document.getElementById('toggleAlertsCfg').addEventListener('click', () => {
    alertsCollapsed = !alertsCollapsed;
    document.getElementById('alertsCfgBody').classList.toggle('sm-hidden', alertsCollapsed);
    document.querySelector('#toggleAlertsCfg .sm-chevron')
            ?.classList.toggle('sm-collapsed', alertsCollapsed);
  });

  const filterInput = document.getElementById('alertFilterInput');
  filterInput.addEventListener('input', () => {
    alertFilter = filterInput.value;
    applyAlertFilter();
  });
  filterInput.addEventListener('click', e => e.stopPropagation());
  applyAlertFilter();
  document.getElementById('runAlertsBtn').addEventListener('click', runAlertSweep);

  const runNotify = document.getElementById('runAlertsNotify');
  runNotify?.addEventListener('change', () =>
    document.getElementById('runNotifyToggle')?.classList.toggle('sm-on', runNotify.checked));

  container.querySelectorAll('.sm-alert-row').forEach(row => {
    row.querySelectorAll('.sm-alert-input').forEach(inp => {
      inp.addEventListener('blur', () => saveAlertRow(row));
      inp.addEventListener('keydown', e => { if (e.key === 'Enter') inp.blur(); });
    });
    const cb = row.querySelector('.sm-alert-enabled');
    cb?.addEventListener('change', () => {
      cb.closest('.sm-notify-toggle')?.classList.toggle('sm-on', cb.checked);
      saveAlertRow(row);
    });
  });
}

function applyAlertFilter() {
  const q = (alertFilter || '').trim().toUpperCase();
  const rows = document.querySelectorAll('#alertsCfgBody .sm-alert-row');
  let visible = 0;
  rows.forEach(row => {
    const hit = !q || row.dataset.symbol.includes(q);
    row.classList.toggle('sm-hidden', !hit);
    if (hit) visible++;
  });
  document.getElementById('alertsEmptyFilter')?.classList.toggle('sm-hidden', visible > 0 || !q);
  const counter = document.getElementById('alertsCount');
  if (counter) counter.textContent = q ? `${visible}/${rows.length}` : `${rows.length}`;
}

// ── Importación de niveles desde planilla ──
let importLevelsFile = null;

function openImportLevelsModal() {
  importLevelsFile = null;
  document.getElementById('importLevelsInput').value = '';
  document.getElementById('importLevelsName').textContent = '';
  document.getElementById('importLevelsStatus').innerHTML = '';
  document.getElementById('runImportLevels').disabled = true;
  document.getElementById('importLevelsModal').classList.remove('sm-hidden');
}

function onImportLevelsFileChosen(e) {
  const f = e.target.files[0];
  if (!f) return;
  importLevelsFile = f;
  document.getElementById('importLevelsName').textContent = f.name;
  document.getElementById('importLevelsStatus').innerHTML = '';
  document.getElementById('runImportLevels').disabled = false;
}

async function runImportLevels() {
  if (!importLevelsFile || !activePortId) return;
  const btn    = document.getElementById('runImportLevels');
  const status = document.getElementById('importLevelsStatus');
  const strict = document.getElementById('importLevelsStrict')?.checked;

  btn.disabled = true;
  btn.innerHTML = '<span class="sm-spinner"></span> Importando…';
  status.innerHTML = '<span class="sm-spinner sm-spinner-dark"></span> Leyendo la planilla…';

  const form = new FormData();
  form.append('file', importLevelsFile);
  form.append('only_portfolio_assets', String(!!strict));

  try {
    const res = await api('POST', `/portfolios/${activePortId}/alerts/import_excel`, form);
    const color = { ok: '#3FB950', skipped: '#8B949E', error: '#F85149' };
    const icon  = { ok: '✓', skipped: '–', error: '⚠' };
    status.innerHTML = `
      <div style="color:#C9D1D9;margin-bottom:8px;">
        ${res.applied} de ${res.total} fila(s) aplicadas
      </div>` + res.summary.map(s => `
      <div style="color:${color[s.status]};margin:2px 0;">
        ${icon[s.status]} <b>${esc(s.symbol)}</b> (fila ${s.row}) — ${esc(s.detail)}
      </div>`).join('');
    if (res.applied > 0) {
      showToast(`✓ ${res.applied} nivel(es) importado(s)`, 'success');
      await loadAndRenderAlerts();
    }
  } catch(err) {
    status.innerHTML = `<span style="color:#F85149;">⚠ ${esc(err.message)}</span>`;
  } finally {
    const b = document.getElementById('runImportLevels');
    if (b) { b.disabled = false; b.textContent = 'Importar'; }
  }
}

function parseLevel(raw) {
  const s = String(raw ?? '').replace(/[$\s]/g, '').replace(',', '.').trim();
  if (!s) return '';
  const n = parseFloat(s);
  return isNaN(n) ? null : String(n);   // null = inválido
}

async function saveAlertRow(row) {
  const symbol = row.dataset.symbol;
  const tgtEl  = row.querySelector('.sm-alert-input[data-field="target"]');
  const stpEl  = row.querySelector('.sm-alert-input[data-field="stop"]');
  const cb     = row.querySelector('.sm-alert-enabled');

  const target = parseLevel(tgtEl.value);
  const stop   = parseLevel(stpEl.value);

  if (target === null) { tgtEl.style.borderColor = '#F85149'; showError(`Target inválido en ${symbol}`); return; }
  if (stop   === null) { stpEl.style.borderColor = '#F85149'; showError(`Stop loss inválido en ${symbol}`); return; }
  tgtEl.style.borderColor = ''; stpEl.style.borderColor = '';

  if (target !== '' && stop !== '' && parseFloat(stop) >= parseFloat(target)) {
    showError(`${symbol}: el stop loss tiene que estar por debajo del target`);
    return;
  }

  // Si se carga un nivel, la alarma se activa sola (si no, quedaba cargada pero muda)
  if ((target !== '' || stop !== '') && cb && !cb.checked) {
    cb.checked = true;
    cb.closest('.sm-notify-toggle')?.classList.add('sm-on');
  }

  try {
    const res = await api('POST', `/portfolios/${activePortId}/alerts/${symbol}`,
      fd({ target_price: target, stop_loss: stop, enabled: String(!!cb?.checked) }));
    // Refresca el estado en memoria
    const idx = alerts.findIndex(a => a.symbol === symbol);
    if (idx >= 0 && res.alert) alerts[idx] = res.alert;
    else if (idx >= 0) { alerts[idx].target_price = null; alerts[idx].stop_loss = null; }
    const saved = row.querySelector('.sm-alert-saved');
    saved.classList.add('sm-show');
    setTimeout(() => saved.classList.remove('sm-show'), 1600);
  } catch(e) { showError(e.message); }
}

async function runAlertSweep() {
  const btn    = document.getElementById('runAlertsBtn');
  const status = document.getElementById('runAlertsStatus');
  const notify = document.getElementById('runAlertsNotify')?.checked || false;
  const box    = document.getElementById('runAlertsResults');

  const hasLevel = a => (a.target_price !== null && a.target_price !== undefined) ||
                        (a.stop_loss    !== null && a.stop_loss    !== undefined);
  const withLevels = alerts.filter(hasLevel);
  const configured = withLevels.filter(a => a.enabled);
  if (configured.length === 0) {
    showError(withLevels.length
      ? `${withLevels.map(a => a.symbol).join(', ')}: tienen niveles cargados pero la alarma está desactivada — marcá "Activa"`
      : 'No hay ningún activo con niveles de precio cargados');
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="sm-spinner"></span> Recorriendo…';
  status.innerHTML = `<span class="sm-spinner sm-spinner-dark"></span>
                      <span>Consultando ${configured.length} activo(s)…</span>`;
  box.innerHTML = '';

  try {
    const res = await api('POST', `/portfolios/${activePortId}/alerts/run`,
      fd({ notify: String(notify) }));
    renderRunResults(res);
    const n = (res.triggered || []).length;
    if (n === 0) {
      status.innerHTML = `<span style="color:#3FB950;">✓ Listo — ningún nivel alcanzado</span>`;
    } else {
      const mail = (res.notified || []).length
        ? `<span style="color:#3FB950;"> · 📨 mail enviado a ${res.notified.length} subscriber(s)</span>`
        : `<span style="color:#F85149;"> · ✗ sin mail: ${esc(res.mail_error || 'notificación desactivada')}</span>`;
      status.innerHTML = `<span style="color:#D29922;">🔔 ${n} nivel(es) alcanzado(s)</span>${mail}`;
    }
    if (n > 0) showToast(`🔔 ${n} alarma(s) de precio`, 'success');
    // Refresca niveles + historial sin perder el informe en pantalla
    const rendered = box.innerHTML, st = status.innerHTML;
    await loadAndRenderAlerts();
    document.getElementById('runAlertsResults').innerHTML = rendered;
    document.getElementById('runAlertsStatus').innerHTML  = st;
  } catch(e) {
    status.innerHTML = `<span style="color:#F85149;">✗ ${esc(e.message)}</span>`;
    showError(e.message);
  } finally {
    const b = document.getElementById('runAlertsBtn');
    if (b) { b.disabled = false; b.textContent = '▶ Correr alarmas'; }
  }
}

function renderRunResults(res) {
  const box = document.getElementById('runAlertsResults');
  let report = res.report || [];
  if (report.length === 0) { box.innerHTML = ''; return; }

  const hits  = report.filter(r => (r.events || []).includes('target')).length;
  const stops = report.filter(r => (r.events || []).includes('stop_loss')).length;

  // El stop loss se muestra primero: es el que pide acción
  const order = { below_stop: 0, above_target: 1, in_range: 2, no_price: 3 };
  report = [...report].sort((a, b) => (order[a.state] ?? 9) - (order[b.state] ?? 9));

  const items = report.map(r => {
    const fired = r.events || [];
    const isNew = (r.new_events || []).length > 0;
    const cls = fired.includes('stop_loss') ? ' sm-fired-stop'
              : fired.includes('target')    ? ' sm-fired-target'
              : r.state === 'no_price'      ? ' sm-no-price' : '';
    const base = ALERT_BADGE[r.state] || ALERT_BADGE.in_range;
    const badge = { cls: base.cls, text: base.text + (isNew && fired.length ? ' · NUEVO' : '') };

    return `
      <div class="sm-run-item${cls}">
        <div class="sm-run-item-sym">${esc(r.symbol)}</div>
        <div class="sm-run-item-detail">
          <span>Precio <b>${fmtNum(r.price)}</b></span>
          <span>Target <b>${fmtNum(r.target)}</b>${
            r.target_gap_pct !== null && r.target_gap_pct !== undefined
              ? ` (${r.target_gap_pct > 0 ? '+' : ''}${fmtNum(r.target_gap_pct)}%)` : ''}</span>
          <span>Stop <b>${fmtNum(r.stop_loss)}</b>${
            r.stop_gap_pct !== null && r.stop_gap_pct !== undefined
              ? ` (${r.stop_gap_pct > 0 ? '+' : ''}${fmtNum(r.stop_gap_pct)}%)` : ''}</span>
          <span style="color:#484F58;">Previo ${fmtNum(r.prev_price)}</span>
        </div>
        <div><span class="sm-run-badge ${badge.cls}">${badge.text}</span></div>
      </div>`;
  }).join('');

  box.innerHTML = `
    <div class="sm-run-summary">
      <div class="sm-run-stat">
        <div class="sm-run-stat-num">${report.length}</div>
        <div class="sm-run-stat-lbl">Revisados</div>
      </div>
      <div class="sm-run-stat sm-hit">
        <div class="sm-run-stat-num">${hits}</div>
        <div class="sm-run-stat-lbl">Take profit</div>
      </div>
      <div class="sm-run-stat sm-stop">
        <div class="sm-run-stat-num">${stops}</div>
        <div class="sm-run-stat-lbl">Stop loss</div>
      </div>
      <div class="sm-run-stat">
        <div class="sm-run-stat-num">${(res.notified || []).length}</div>
        <div class="sm-run-stat-lbl">Mails</div>
      </div>
    </div>
    <div class="sm-run-results">${items}</div>`;
}


// ══════════════════════════════════════════════════
//  MODAL DE CONFIRMACIÓN
// ══════════════════════════════════════════════════
let confirmResolver = null;

function smConfirm({ title = 'Confirmar', text = '¿Seguro?', sub = '',
                     okLabel = 'Confirmar', danger = false } = {}) {
  return new Promise(resolve => {
    // Si ya había uno abierto, se resuelve en falso
    if (confirmResolver) { confirmResolver(false); }
    confirmResolver = resolve;
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmText').textContent  = text;
    const subEl = document.getElementById('confirmSub');
    subEl.textContent = sub;
    subEl.classList.toggle('sm-hidden', !sub);
    const ok = document.getElementById('confirmOkBtn');
    ok.textContent = okLabel;
    ok.className = 'sm-btn ' + (danger ? 'sm-btn-danger' : 'sm-btn-primary');
    document.getElementById('confirmModal').classList.remove('sm-hidden');
    setTimeout(() => ok.focus(), 80);
  });
}

function resolveConfirm(value) {
  closeModal('confirmModal');
  if (confirmResolver) { const r = confirmResolver; confirmResolver = null; r(value); }
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
  document.getElementById('tabAlerts').addEventListener('click', () => switchTab('alerts'));
  document.getElementById('tabEmails').addEventListener('click', () => switchTab('emails'));

  // Cerrar el panel del gráfico pide confirmación (se apretaba por error)
  document.getElementById('closeChartBtn').addEventListener('click', async () => {
    const ok = await smConfirm({
      title: 'Cerrar panel',
      text: `¿Cerrar el panel de ${activeAsset ? activeAsset.symbol : 'este activo'}?`,
      sub: 'Se cierran el gráfico, las notas y los comentarios. Nada de lo guardado se pierde.',
      okLabel: 'Cerrar panel',
      danger: true,
    });
    if (ok) hideChart();
  });

  // ── Modal de importación de niveles ──
  document.getElementById('closeImportLevelsModal').addEventListener('click', () => closeModal('importLevelsModal'));
  document.getElementById('cancelImportLevels').addEventListener('click', () => closeModal('importLevelsModal'));
  document.getElementById('importLevelsModal').addEventListener('click', e => {
    if (e.target.id === 'importLevelsModal') closeModal('importLevelsModal');
  });
  document.getElementById('importLevelsInput').addEventListener('change', onImportLevelsFileChosen);
  document.getElementById('runImportLevels').addEventListener('click', runImportLevels);
  const strictCb = document.getElementById('importLevelsStrict');
  strictCb.addEventListener('change', () =>
    document.getElementById('importLevelsStrictToggle').classList.toggle('sm-on', strictCb.checked));

  // ── Modal de confirmación ──
  document.getElementById('confirmOkBtn').addEventListener('click', () => resolveConfirm(true));
  document.getElementById('confirmCancelBtn').addEventListener('click', () => resolveConfirm(false));
  document.getElementById('confirmCloseX').addEventListener('click', () => resolveConfirm(false));
  document.getElementById('confirmModal').addEventListener('click', e => {
    if (e.target.id === 'confirmModal') resolveConfirm(false);
  });

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

  // ── Import Excel modal ─────────────────────────────────
  document.getElementById('importExcelBtn').addEventListener('click', openImportExcelModal);
  document.getElementById('closeImportExcelModal').addEventListener('click', () => closeModal('importExcelModal'));
  document.getElementById('cancelImportExcel').addEventListener('click', () => closeModal('importExcelModal'));
  document.getElementById('importExcelModal').addEventListener('click', e => { if (e.target.id==='importExcelModal') closeModal('importExcelModal'); });
  document.getElementById('importExcelInput').addEventListener('change', onImportExcelFileChosen);
  document.getElementById('runImportExcel').addEventListener('click', runImportExcel);
  document.querySelectorAll('input[name="importExcelMode"]').forEach(r => {
    r.addEventListener('change', () => {
      const isMerge = document.querySelector('input[name="importExcelMode"]:checked').value === 'merge';
      document.getElementById('importExcelSymbolsField').classList.toggle('sm-hidden', !isMerge);
    });
  });
  document.getElementById('researchCellNumber').addEventListener('keydown', e => { if (e.key==='Enter') saveCellEdit(); });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (!document.getElementById('confirmModal')?.classList.contains('sm-hidden')) {
        resolveConfirm(false);
      }
      ['portfolioModal','assetModal','researchCellModal','researchTopicModal','importExcelModal']
        .forEach(id => closeModal(id));
    }
  });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
