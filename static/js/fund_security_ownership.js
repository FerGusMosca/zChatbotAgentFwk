// fund_security_ownership.js — Bias dark theme
// v2 — Neo4j connection feedback, pre-computed aggregates, Q/Q transitions,
//      new positions and size bucketing. All original logic preserved.

const BASE_URL = '/fund_security_ownership';

const els = {
  // Period
  yearSelect:       document.getElementById('yearSelect'),
  quarterSelect:    document.getElementById('quarterSelect'),
  periodStatus:     document.getElementById('periodStatus'),
  periodLoader:     document.getElementById('periodLoader'),
  periodLoaderTitle:document.getElementById('periodLoaderTitle'),
  periodLoaderDetail:document.getElementById('periodLoaderDetail'),

  // Tabs
  tabs:             document.querySelectorAll('.fso-tab'),
  tabContents:      document.querySelectorAll('.fso-tab-content'),

  // Crowded
  crowdedOffset:    document.getElementById('crowdedOffset'),
  crowdedMinScore:  document.getElementById('crowdedMinScore'),
  crowdedSize:      document.getElementById('crowdedSize'),
  crowdedLimit:     document.getElementById('crowdedLimit'),
  crowdedSearchBtn: document.getElementById('crowdedSearchBtn'),

  // Capitulation
  capMinOwners:     document.getElementById('capMinOwners'),
  capOffset:        document.getElementById('capOffset'),
  capSize:          document.getElementById('capSize'),
  capLimit:         document.getElementById('capLimit'),
  capSearchBtn:     document.getElementById('capSearchBtn'),

  // Transitions
  trFromYear:       document.getElementById('trFromYear'),
  trFromQuarter:    document.getElementById('trFromQuarter'),
  trToYear:         document.getElementById('trToYear'),
  trToQuarter:      document.getElementById('trToQuarter'),
  trDirection:      document.getElementById('trDirection'),
  trMinJump:        document.getElementById('trMinJump'),
  trMinOwners:      document.getElementById('trMinOwners'),
  trSize:           document.getElementById('trSize'),
  trLimit:          document.getElementById('trLimit'),
  trSearchBtn:      document.getElementById('trSearchBtn'),
  trMatrixBtn:      document.getElementById('trMatrixBtn'),
  trMatrixBox:      document.getElementById('trMatrixBox'),

  // New positions
  npFromYear:       document.getElementById('npFromYear'),
  npFromQuarter:    document.getElementById('npFromQuarter'),
  npToYear:         document.getElementById('npToYear'),
  npToQuarter:      document.getElementById('npToQuarter'),
  npMinOwners:      document.getElementById('npMinOwners'),
  npBrandNew:       document.getElementById('npBrandNew'),
  npSize:           document.getElementById('npSize'),
  npLimit:          document.getElementById('npLimit'),
  npSearchBtn:      document.getElementById('npSearchBtn'),

  // Size
  sizeSearchBtn:    document.getElementById('sizeSearchBtn'),

  // Data / aggregates
  buildCurrentBtn:  document.getElementById('buildCurrentBtn'),
  buildAllBtn:      document.getElementById('buildAllBtn'),
  refreshStatusBtn: document.getElementById('refreshStatusBtn'),
  buildProgress:    document.getElementById('buildProgress'),
  aggregatesTable:  document.getElementById('aggregatesTable'),

  // Portfolio
  portfolioManager: document.getElementById('portfolioManager'),
  managerSuggestions:document.getElementById('managerSuggestions'),
  portfolioLimit:   document.getElementById('portfolioLimit'),
  portfolioSearchBtn:document.getElementById('portfolioSearchBtn'),
  selectedManager:  document.getElementById('selectedManager'),

  // Ownership
  ownershipAsset:   document.getElementById('ownershipAsset'),
  assetSuggestions: document.getElementById('assetSuggestions'),
  ownershipLimit:   document.getElementById('ownershipLimit'),
  ownershipSearchBtn:document.getElementById('ownershipSearchBtn'),
  selectedAsset:    document.getElementById('selectedAsset'),
  assetStats:       document.getElementById('assetStats'),

  // Results
  resultMessage:    document.getElementById('resultMessage'),
  resultsContainer: document.getElementById('resultsContainer'),
  resultsTitle:     document.getElementById('resultsTitle'),
  paginationInfo:   document.getElementById('paginationInfo'),
  tableHead:        document.getElementById('tableHead'),
  tableBody:        document.getElementById('tableBody'),
  prevPageBtn:      document.getElementById('prevPageBtn'),
  nextPageBtn:      document.getElementById('nextPageBtn'),
  pageInfo:         document.getElementById('pageInfo'),
  exportContainer:  document.getElementById('exportContainer'),
  exportCsvBtn:     document.getElementById('exportCsvBtn'),
};

// State
let currentTab        = 'crowded';
let currentData       = [];
let currentPagination = null;
let currentQueryType  = null;
let debounceTimer     = null;
let selectedManagerData = null;
let selectedAssetData   = null;
let availablePeriods    = [];
let buildPollTimer      = null;

const TIER_LABELS = {
  1: 'T1 Mega crowded',
  2: 'T2 Crowded',
  3: 'T3 Moderate',
  4: 'T4 Light',
  5: 'T5 Abandoned',
};

const ACTION_BUTTONS = [
  'crowdedSearchBtn', 'capSearchBtn', 'trSearchBtn', 'trMatrixBtn',
  'npSearchBtn', 'sizeSearchBtn', 'portfolioSearchBtn', 'ownershipSearchBtn',
  'buildCurrentBtn', 'buildAllBtn',
];

// ══════════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════════
function init() {
  setQueriesEnabled(false);
  loadAvailablePeriods();
  setupTabListeners();
  setupSearchListeners();
  setupPaginationListeners();
  setupSuggestionListeners();
  setupExportListener();
  setupDataListeners();
}

// ══════════════════════════════════════════════════
//  +1 — PERIODS WITH VISIBLE NEO4J HANDSHAKE
// ══════════════════════════════════════════════════
function setQueriesEnabled(enabled) {
  els.yearSelect.disabled    = !enabled;
  els.quarterSelect.disabled = !enabled;
  ACTION_BUTTONS.forEach(id => {
    const b = els[id];
    if (b) b.disabled = !enabled;
  });
}

function showPeriodLoader(title, detail) {
  els.periodLoaderTitle.textContent  = title;
  els.periodLoaderDetail.textContent = detail;
  els.periodLoader.classList.add('active');
  els.periodLoader.classList.remove('error');
}

function hidePeriodLoader() {
  els.periodLoader.classList.remove('active');
}

function failPeriodLoader(title, detail) {
  els.periodLoaderTitle.textContent  = title;
  els.periodLoaderDetail.textContent = detail;
  els.periodLoader.classList.add('active', 'error');
}

async function loadAvailablePeriods() {
  const t0 = performance.now();
  showPeriodLoader(
    'Connecting to Neo4j…',
    'Reading available 13F periods from the graph. Queries stay disabled until this finishes.'
  );
  els.periodStatus.textContent = '⏳ loading…';
  els.periodStatus.style.color = '#8B949E';

  try {
    const response = await fetch(`${BASE_URL}/available_periods`);
    const data = await response.json();

    if (data.status === 'ok' && data.periods.length > 0) {
      availablePeriods = data.periods.filter(p =>
        p.year && p.quarter && p.year !== 'None' && p.quarter !== 'None');
      data.periods = availablePeriods;
      if (availablePeriods.length === 0) {
        failPeriodLoader('No valid periods', 'Every period came back null.');
        return;
      }
      const years = [...new Set(data.periods.map(p => String(p.year)))]
        .sort((a, b) => b.localeCompare(a));

      els.yearSelect.innerHTML = '<option value="" disabled selected>Year</option>';
      years.forEach(year => {
        const opt = document.createElement('option');
        opt.value = opt.textContent = year;
        els.yearSelect.appendChild(opt);
      });

      els.yearSelect.value    = String(data.periods[0].year);
      els.quarterSelect.value = String(data.periods[0].quarter);

      fillPeriodPair(els.trToYear,   els.trToQuarter,   years, data.periods[0]);
      fillPeriodPair(els.trFromYear, els.trFromQuarter, years, previousPeriod(data.periods[0]));
      fillPeriodPair(els.npToYear,   els.npToQuarter,   years, data.periods[0]);
      fillPeriodPair(els.npFromYear, els.npFromQuarter, years, previousPeriod(data.periods[0]));

      const secs = ((performance.now() - t0) / 1000).toFixed(1);
      els.periodStatus.textContent = `✓ ${data.periods.length} periods`;
      els.periodStatus.style.color = '#3FB950';
      hidePeriodLoader();
      setQueriesEnabled(true);
      showResult(`Graph ready — ${data.periods.length} periods loaded in ${secs}s`, 'success');
      loadAggregatesStatus();
    } else {
      failPeriodLoader('No periods found', 'The graph answered but has no HOLDS relationships yet.');
      els.periodStatus.textContent = '✗ empty';
      els.periodStatus.style.color = '#F85149';
    }
  } catch (err) {
    console.error('Failed to load periods:', err);
    failPeriodLoader('Could not reach Neo4j', String(err.message || err));
    els.periodStatus.textContent  = '✗ Error';
    els.periodStatus.style.color  = '#F85149';
  }
}

function previousPeriod(p) {
  const y = parseInt(p.year, 10);
  const q = parseInt(p.quarter, 10);
  return q > 1 ? { year: String(y), quarter: String(q - 1) }
               : { year: String(y - 1), quarter: '4' };
}

function fillPeriodPair(yearSel, quarterSel, years, preset) {
  if (!yearSel) return;
  yearSel.innerHTML = '';
  years.forEach(year => {
    const opt = document.createElement('option');
    opt.value = opt.textContent = year;
    yearSel.appendChild(opt);
  });
  if (preset) {
    if (years.includes(String(preset.year))) yearSel.value = String(preset.year);
    quarterSel.value = String(preset.quarter);
  }
}

// ══════════════════════════════════════════════════
//  TABS
// ══════════════════════════════════════════════════
function setupTabListeners() {
  els.tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const tabId = tab.dataset.tab;
      els.tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      els.tabContents.forEach(c => {
        c.classList.remove('active');
        if (c.id === `tab-${tabId}`) c.classList.add('active');
      });
      currentTab = tabId;
      clearResults();
      if (tabId === 'data') loadAggregatesStatus();
    });
  });
}

// ══════════════════════════════════════════════════
//  SEARCH LISTENERS
// ══════════════════════════════════════════════════
function setupSearchListeners() {
  els.crowdedSearchBtn.addEventListener('click',  () => searchCrowdedTrades());
  els.capSearchBtn.addEventListener('click',      () => searchCapitulation());
  els.trSearchBtn.addEventListener('click',       () => searchTransitions());
  els.trMatrixBtn.addEventListener('click',       () => loadTransitionMatrix());
  els.npSearchBtn.addEventListener('click',       () => searchNewPositions());
  els.sizeSearchBtn.addEventListener('click',     () => searchSizeBuckets());
  els.portfolioSearchBtn.addEventListener('click',() => searchPortfolio());
  els.ownershipSearchBtn.addEventListener('click',() => searchAssetOwnership());
}

function setupPaginationListeners() {
  els.prevPageBtn.addEventListener('click', () => changePage(-1));
  els.nextPageBtn.addEventListener('click', () => changePage(1));
}

function setupExportListener() {
  els.exportCsvBtn.addEventListener('click', exportToCsv);
}

// ══════════════════════════════════════════════════
//  AUTOCOMPLETE
// ══════════════════════════════════════════════════
function setupSuggestionListeners() {
  els.portfolioManager.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => searchManagers(els.portfolioManager.value), 300);
  });
  els.portfolioManager.addEventListener('focus', () => {
    if (els.managerSuggestions.children.length > 0) els.managerSuggestions.classList.add('active');
  });

  els.ownershipAsset.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => searchAssets(els.ownershipAsset.value), 300);
  });
  els.ownershipAsset.addEventListener('focus', () => {
    if (els.assetSuggestions.children.length > 0) els.assetSuggestions.classList.add('active');
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('.fso-control-group')) {
      els.managerSuggestions.classList.remove('active');
      els.assetSuggestions.classList.remove('active');
    }
  });
}

async function searchManagers(query) {
  if (!query || query.length < 2) { els.managerSuggestions.classList.remove('active'); return; }
  try {
    const fd = new FormData(); fd.append('query', query);
    const resp = await fetch(`${BASE_URL}/search_managers`, { method: 'POST', body: fd });
    const data = await resp.json();

    if (data.status === 'ok' && data.managers.length > 0) {
      els.managerSuggestions.innerHTML = data.managers.map(m => `
        <div class="fso-suggestion-item" data-cik="${m.cik}" data-name="${escapeHtml(m.name)}">
          <span class="name">${escapeHtml(m.name)}</span>
        </div>`).join('');

      els.managerSuggestions.querySelectorAll('.fso-suggestion-item').forEach(item => {
        item.addEventListener('click', () => {
          selectedManagerData = { cik: item.dataset.cik, name: item.dataset.name };
          els.portfolioManager.value = item.dataset.name;
          els.managerSuggestions.classList.remove('active');
          els.selectedManager.textContent = `${item.dataset.name}`;
          els.selectedManager.classList.add('active');
        });
      });
      els.managerSuggestions.classList.add('active');
    } else {
      els.managerSuggestions.classList.remove('active');
    }
  } catch (err) { console.error('Manager search failed:', err); }
}

async function searchAssets(query) {
  if (!query || query.length < 2) { els.assetSuggestions.classList.remove('active'); return; }
  try {
    const fd = new FormData(); fd.append('query', query);
    const resp = await fetch(`${BASE_URL}/search_assets`, { method: 'POST', body: fd });
    const data = await resp.json();

    if (data.status === 'ok' && data.assets.length > 0) {
      els.assetSuggestions.innerHTML = data.assets.map(a => `
        <div class="fso-suggestion-item" data-cusip="${a.cusip}" data-name="${escapeHtml(a.name)}">
          <span class="ticker">${a.cusip}</span>
          <span class="name">${escapeHtml(a.name)}</span>
        </div>`).join('');

      els.assetSuggestions.querySelectorAll('.fso-suggestion-item').forEach(item => {
        item.addEventListener('click', () => {
          selectedAssetData = { cusip: item.dataset.cusip, name: item.dataset.name };
          els.ownershipAsset.value = item.dataset.name;
          els.assetSuggestions.classList.remove('active');
          els.selectedAsset.textContent = `${item.dataset.cusip} — ${item.dataset.name}`;
          els.selectedAsset.classList.add('active');
        });
      });
      els.assetSuggestions.classList.add('active');
    } else {
      els.assetSuggestions.classList.remove('active');
    }
  } catch (err) { console.error('Asset search failed:', err); }
}

// ══════════════════════════════════════════════════
//  VALIDATE PERIOD
// ══════════════════════════════════════════════════
function validatePeriod() {
  if (!els.yearSelect.value || !els.quarterSelect.value) {
    showResult('Select Year and Quarter first', 'error');
    return false;
  }
  return true;
}

// ══════════════════════════════════════════════════
//  SEARCH #1 — CROWDED TRADES
// ══════════════════════════════════════════════════
async function searchCrowdedTrades(offset = null) {
  if (!validatePeriod()) return;
  const btn = els.crowdedSearchBtn;
  btn.classList.add('loading'); btn.disabled = true;
  try {
    const fd = new FormData();
    fd.append('year',    els.yearSelect.value);
    fd.append('quarter', els.quarterSelect.value);
    fd.append('offset',  offset !== null ? offset : els.crowdedOffset.value);
    fd.append('limit',   els.crowdedLimit.value);
    if (els.crowdedMinScore.value) fd.append('min_crowd_score', els.crowdedMinScore.value);
    if (els.crowdedSize.value)     fd.append('size_bucket', els.crowdedSize.value);

    const resp = await fetch(`${BASE_URL}/crowded_trades`, { method: 'POST', body: fd });
    const data = await resp.json();

    if (data.status === 'ok') {
      currentData = data.data; currentPagination = data.pagination; currentQueryType = 'crowded';
      displayCrowdedResults(data);
      showResult(`${data.pagination.total.toLocaleString()} assets found`, 'success');
    } else {
      showResult(data.message || 'Search failed', 'error');
    }
  } catch (err) { showResult(`Error: ${err.message}`, 'error'); }
  finally { btn.classList.remove('loading'); btn.disabled = false; }
}

// ══════════════════════════════════════════════════
//  SEARCH #2 — CAPITULATION
// ══════════════════════════════════════════════════
async function searchCapitulation(offset = null) {
  if (!validatePeriod()) return;
  const btn = els.capSearchBtn;
  btn.classList.add('loading'); btn.disabled = true;
  try {
    const fd = new FormData();
    fd.append('year',       els.yearSelect.value);
    fd.append('quarter',    els.quarterSelect.value);
    fd.append('offset',     offset !== null ? offset : els.capOffset.value);
    fd.append('limit',      els.capLimit.value);
    fd.append('min_owners', els.capMinOwners.value);
    if (els.capSize.value) fd.append('size_bucket', els.capSize.value);

    const resp = await fetch(`${BASE_URL}/capitulation_trades`, { method: 'POST', body: fd });
    const data = await resp.json();

    if (data.status === 'ok') {
      currentData = data.data; currentPagination = data.pagination; currentQueryType = 'capitulation';
      displayCrowdedResults(data);
      showResult(`${data.pagination.total.toLocaleString()} assets (min ${data.query_params.min_owners} owners)`, 'success');
    } else {
      showResult(data.message || 'Search failed', 'error');
    }
  } catch (err) { showResult(`Error: ${err.message}`, 'error'); }
  finally { btn.classList.remove('loading'); btn.disabled = false; }
}

// ══════════════════════════════════════════════════
//  SEARCH #5 — CROWD TRANSITIONS
// ══════════════════════════════════════════════════
function transitionParams(offset) {
  const fd = new FormData();
  fd.append('from_year',     els.trFromYear.value);
  fd.append('from_quarter',  els.trFromQuarter.value);
  fd.append('to_year',       els.trToYear.value);
  fd.append('to_quarter',    els.trToQuarter.value);
  fd.append('direction',     els.trDirection.value);
  fd.append('min_tier_jump', els.trMinJump.value);
  fd.append('min_owners',    els.trMinOwners.value);
  fd.append('offset',        offset);
  fd.append('limit',         els.trLimit.value);
  if (els.trSize.value) fd.append('size_bucket', els.trSize.value);
  return fd;
}

async function searchTransitions(offset = 0) {
  const btn = els.trSearchBtn;
  btn.classList.add('loading'); btn.disabled = true;
  try {
    const resp = await fetch(`${BASE_URL}/crowd_transitions`, {
      method: 'POST', body: transitionParams(offset)
    });
    const data = await resp.json();

    if (data.status === 'ok') {
      currentData = data.data; currentPagination = data.pagination; currentQueryType = 'transitions';
      displayTransitionResults(data);
      showResult(
        `${data.pagination.total.toLocaleString()} assets changed tier · ${data.query_params.from} → ${data.query_params.to}`,
        data.pagination.total ? 'success' : 'info'
      );
    } else {
      showResult(data.message || 'Search failed', 'error');
      if (data.needs_build) showResult(data.message + ' — see the Data tab', 'error');
    }
  } catch (err) { showResult(`Error: ${err.message}`, 'error'); }
  finally { btn.classList.remove('loading'); btn.disabled = false; }
}

async function loadTransitionMatrix() {
  const btn = els.trMatrixBtn;
  btn.disabled = true;
  try {
    const fd = new FormData();
    fd.append('from_year',    els.trFromYear.value);
    fd.append('from_quarter', els.trFromQuarter.value);
    fd.append('to_year',      els.trToYear.value);
    fd.append('to_quarter',   els.trToQuarter.value);

    const resp = await fetch(`${BASE_URL}/transition_matrix`, { method: 'POST', body: fd });
    const data = await resp.json();

    if (data.status !== 'ok') { showResult(data.message || 'Matrix failed', 'error'); return; }

    const cells = {};
    let max = 0;
    data.matrix.forEach(m => {
      cells[`${m.from_tier}-${m.to_tier}`] = m.assets;
      if (m.assets > max) max = m.assets;
    });

    let html = '<table class="fso-matrix"><thead><tr><th>from \\ to</th>';
    for (let t = 1; t <= 5; t++) html += `<th>${TIER_LABELS[t]}</th>`;
    html += '</tr></thead><tbody>';
    for (let f = 1; f <= 5; f++) {
      html += `<tr><th>${TIER_LABELS[f]}</th>`;
      for (let t = 1; t <= 5; t++) {
        const v = cells[`${f}-${t}`] || 0;
        const alpha = max ? (v / max) : 0;
        const cls = f === t ? 'diag' : (t < f ? 'up' : 'down');
        html += `<td class="${cls}" style="--w:${alpha.toFixed(3)}">${v.toLocaleString()}</td>`;
      }
      html += '</tr>';
    }
    html += '</tbody></table>';

    els.trMatrixBox.innerHTML = html;
    els.trMatrixBox.classList.add('active');
  } catch (err) { showResult(`Error: ${err.message}`, 'error'); }
  finally { btn.disabled = false; }
}

// ══════════════════════════════════════════════════
//  SEARCH #6 — NEW POSITIONS
// ══════════════════════════════════════════════════
async function searchNewPositions(offset = 0) {
  const btn = els.npSearchBtn;
  btn.classList.add('loading'); btn.disabled = true;
  try {
    const fd = new FormData();
    fd.append('from_year',      els.npFromYear.value);
    fd.append('from_quarter',   els.npFromQuarter.value);
    fd.append('to_year',        els.npToYear.value);
    fd.append('to_quarter',     els.npToQuarter.value);
    fd.append('min_owners',     els.npMinOwners.value);
    fd.append('brand_new_only', els.npBrandNew.value);
    fd.append('offset',         offset);
    fd.append('limit',          els.npLimit.value);
    if (els.npSize.value) fd.append('size_bucket', els.npSize.value);

    const resp = await fetch(`${BASE_URL}/new_positions`, { method: 'POST', body: fd });
    const data = await resp.json();

    if (data.status === 'ok') {
      currentData = data.data; currentPagination = data.pagination; currentQueryType = 'newpos';
      displayNewPositionResults(data);
      showResult(
        `${data.pagination.total.toLocaleString()} new positions · ${data.query_params.from} → ${data.query_params.to}`,
        data.pagination.total ? 'success' : 'info'
      );
    } else {
      showResult(data.message || 'Search failed', 'error');
    }
  } catch (err) { showResult(`Error: ${err.message}`, 'error'); }
  finally { btn.classList.remove('loading'); btn.disabled = false; }
}

// ══════════════════════════════════════════════════
//  SEARCH #7 — SIZE BUCKETS
// ══════════════════════════════════════════════════
async function searchSizeBuckets() {
  if (!validatePeriod()) return;
  const btn = els.sizeSearchBtn;
  btn.classList.add('loading'); btn.disabled = true;
  try {
    const fd = new FormData();
    fd.append('year',    els.yearSelect.value);
    fd.append('quarter', els.quarterSelect.value);

    const resp = await fetch(`${BASE_URL}/size_buckets`, { method: 'POST', body: fd });
    const data = await resp.json();

    if (data.status === 'ok') {
      currentData = data.data;
      currentPagination = { offset: 0, limit: data.data.length || 1,
                            total: data.data.length, has_more: false };
      currentQueryType = 'size';
      displaySizeResults(data);
      showResult(data.note, 'info');
    } else {
      showResult(data.message || 'Search failed', 'error');
    }
  } catch (err) { showResult(`Error: ${err.message}`, 'error'); }
  finally { btn.classList.remove('loading'); btn.disabled = false; }
}

// ══════════════════════════════════════════════════
//  SEARCH #3 — PORTFOLIO
// ══════════════════════════════════════════════════
async function searchPortfolio(offset = 0) {
  if (!validatePeriod()) return;
  const managerName = els.portfolioManager.value.trim();
  if (!managerName) { showResult('Enter a fund/manager name', 'error'); return; }

  const btn = els.portfolioSearchBtn;
  btn.classList.add('loading'); btn.disabled = true;
  try {
    const fd = new FormData();
    fd.append('manager_name', managerName);
    fd.append('year',    els.yearSelect.value);
    fd.append('quarter', els.quarterSelect.value);
    fd.append('offset',  offset);
    fd.append('limit',   els.portfolioLimit.value);

    const resp = await fetch(`${BASE_URL}/portfolio_viewer`, { method: 'POST', body: fd });
    const data = await resp.json();

    if (data.status === 'ok') {
      currentData = data.data; currentPagination = data.pagination; currentQueryType = 'portfolio';
      if (data.selected_manager) {
        els.selectedManager.textContent = data.selected_manager.name;
        els.selectedManager.classList.add('active');
        selectedManagerData = data.selected_manager;
      }
      displayPortfolioResults(data);
      showResult(
        data.data.length === 0
          ? (data.message || 'No holdings found')
          : `${data.pagination.total.toLocaleString()} holdings`,
        data.data.length === 0 ? 'info' : 'success'
      );
    } else {
      showResult(data.message || 'Search failed', 'error');
    }
  } catch (err) { showResult(`Error: ${err.message}`, 'error'); }
  finally { btn.classList.remove('loading'); btn.disabled = false; }
}

// ══════════════════════════════════════════════════
//  SEARCH #4 — ASSET OWNERSHIP
// ══════════════════════════════════════════════════
async function searchAssetOwnership(offset = 0) {
  if (!validatePeriod()) return;
  const assetId = els.ownershipAsset.value.trim();
  if (!assetId) { showResult('Enter an asset identifier', 'error'); return; }

  const btn = els.ownershipSearchBtn;
  btn.classList.add('loading'); btn.disabled = true;
  try {
    const fd = new FormData();
    fd.append('asset_identifier', assetId);
    fd.append('year',    els.yearSelect.value);
    fd.append('quarter', els.quarterSelect.value);
    fd.append('offset',  offset);
    fd.append('limit',   els.ownershipLimit.value);

    const resp = await fetch(`${BASE_URL}/asset_ownership`, { method: 'POST', body: fd });
    const data = await resp.json();

    if (data.status === 'ok') {
      currentData = data.data; currentPagination = data.pagination; currentQueryType = 'ownership';
      if (data.selected_asset) {
        els.selectedAsset.textContent = `${data.selected_asset.ticker || ''} — ${data.selected_asset.name}`.trim().replace(/^—\s/, '');
        els.selectedAsset.classList.add('active');
        selectedAssetData = data.selected_asset;
      }
      if (data.stats) displayAssetStats(data.stats);
      displayOwnershipResults(data);
      showResult(
        data.data.length === 0
          ? (data.message || 'No owners found')
          : `${data.stats?.total_owners?.toLocaleString() || data.pagination.total} institutional owners`,
        data.data.length === 0 ? 'info' : 'success'
      );
    } else {
      showResult(data.message || 'Search failed', 'error');
    }
  } catch (err) { showResult(`Error: ${err.message}`, 'error'); }
  finally { btn.classList.remove('loading'); btn.disabled = false; }
}

// ══════════════════════════════════════════════════
//  +3 — AGGREGATES (Data tab)
// ══════════════════════════════════════════════════
function setupDataListeners() {
  els.buildCurrentBtn.addEventListener('click', () => {
    if (!validatePeriod()) return;
    startBuild({ year: els.yearSelect.value, quarter: els.quarterSelect.value });
  });
  els.buildAllBtn.addEventListener('click', () => {
    if (!confirm('Rebuild the aggregate snapshot for EVERY period? This walks the whole graph once per period.')) return;
    startBuild({ rebuild_all: 1 });
  });
  els.refreshStatusBtn.addEventListener('click', () => loadAggregatesStatus());
}

async function startBuild(params) {
  const fd = new FormData();
  Object.entries(params).forEach(([k, v]) => fd.append(k, v));

  els.buildCurrentBtn.disabled = true;
  els.buildAllBtn.disabled = true;
  try {
    const resp = await fetch(`${BASE_URL}/build_aggregates`, { method: 'POST', body: fd });
    const data = await resp.json();
    if (data.status !== 'ok') {
      showResult(data.message || 'Build failed', 'error');
      els.buildCurrentBtn.disabled = false;
      els.buildAllBtn.disabled = false;
      return;
    }
    showResult(`Build queued for ${data.queued} period(s)`, 'info');
    pollBuild();
  } catch (err) {
    showResult(`Error: ${err.message}`, 'error');
    els.buildCurrentBtn.disabled = false;
    els.buildAllBtn.disabled = false;
  }
}

function pollBuild() {
  clearInterval(buildPollTimer);
  buildPollTimer = setInterval(loadAggregatesStatus, 2500);
  loadAggregatesStatus();
}

async function loadAggregatesStatus() {
  try {
    const resp = await fetch(`${BASE_URL}/aggregates_status`);
    const data = await resp.json();
    if (data.status !== 'ok') return;

    renderBuildProgress(data.build);
    renderAggregatesTable(data.periods);

    if (!data.build.running) {
      clearInterval(buildPollTimer);
      buildPollTimer = null;
      els.buildCurrentBtn.disabled = false;
      els.buildAllBtn.disabled = false;
    }
  } catch (err) {
    console.error('aggregates status failed', err);
  }
}

function renderBuildProgress(build) {
  if (!build) return;
  if (!build.running && build.done.length === 0 && build.failed.length === 0) {
    els.buildProgress.classList.remove('active');
    els.buildProgress.innerHTML = '';
    return;
  }

  const lines = [];
  if (build.running) {
    lines.push(`<div class="fso-build-line running">
      <div class="fso-loader-spinner small"></div>
      <span>${escapeHtml(build.message || 'working…')}</span></div>`);
  }
  build.done.forEach(d => {
    lines.push(`<div class="fso-build-line ok">✓ ${escapeHtml(d.period)} — ${d.assets.toLocaleString()} assets</div>`);
  });
  build.failed.forEach(f => {
    lines.push(`<div class="fso-build-line err">✗ ${escapeHtml(f.period)} — ${escapeHtml(f.error)}</div>`);
  });

  els.buildProgress.innerHTML = lines.join('');
  els.buildProgress.classList.add('active');
}

function renderAggregatesTable(periods) {
  if (!periods || periods.length === 0) {
    els.aggregatesTable.innerHTML = '';
    return;
  }
  els.aggregatesTable.innerHTML = `
    <table class="fso-table">
      <thead><tr>
        <th>Period</th><th class="numeric">Assets</th><th>Status</th><th>Built at (UTC)</th>
      </tr></thead>
      <tbody>
        ${periods.map(p => `<tr>
          <td class="ticker">${escapeHtml(p.year)} Q${escapeHtml(p.quarter)}</td>
          <td class="numeric">${p.assets ? p.assets.toLocaleString() : '—'}</td>
          <td>${p.built ? '<span class="fso-badge ok">ready</span>'
                        : '<span class="fso-badge pending">not built</span>'}</td>
          <td style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:#6E7681;">${p.built_at ? escapeHtml(p.built_at) : '—'}</td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

// ══════════════════════════════════════════════════
//  DISPLAY FUNCTIONS
// ══════════════════════════════════════════════════
function displayCrowdedResults(data) {
  const isCrowded = currentQueryType === 'crowded';
  els.resultsTitle.textContent = isCrowded ? 'Crowded Trades Ranking' : 'Capitulation Ranking';

  els.tableHead.innerHTML = `<tr>
    <th>Rank</th>
    <th>Asset</th>
    <th class="numeric">Owners</th>
    <th class="numeric">Total Weight</th>
    <th class="numeric">Crowd Score</th>
  </tr>`;

  els.tableBody.innerHTML = data.data.map(row => `<tr>
    <td class="rank">${row.rank}</td>
    <td class="ticker">${escapeHtml(row.asset || 'Unknown')}</td>
    <td class="numeric owners">${row.owners.toLocaleString()}</td>
    <td class="numeric weight">${formatNum(row.total_weight)}</td>
    <td class="numeric crowd-score">${formatNum(row.crowd_score)}</td>
  </tr>`).join('');

  updatePagination(data.pagination);
  els.resultsContainer.classList.add('active');
  els.exportContainer.classList.remove('fso-hidden');
}

function displayTransitionResults(data) {
  els.resultsTitle.textContent =
    `Crowding Transitions — ${data.query_params.from} → ${data.query_params.to}`;

  els.tableHead.innerHTML = `<tr>
    <th>Rank</th>
    <th>Asset</th>
    <th>Size</th>
    <th>Tier move</th>
    <th class="numeric">Owners</th>
    <th class="numeric">Δ Owners</th>
    <th class="numeric">Δ Weight</th>
    <th class="numeric">Crowd Score</th>
  </tr>`;

  els.tableBody.innerHTML = data.data.map(row => {
    const up = row.tier_delta > 0;
    const arrow = up ? '▲' : '▼';
    const cls = up ? 'pos' : 'neg';
    return `<tr>
      <td class="rank">${row.rank}</td>
      <td class="ticker">${escapeHtml(row.asset || 'Unknown')}</td>
      <td><span class="fso-badge size">${escapeHtml(row.size_bucket || '—')}</span></td>
      <td class="${cls}">${arrow} T${row.from_tier} → T${row.to_tier}</td>
      <td class="numeric">${row.from_owners.toLocaleString()} → ${row.to_owners.toLocaleString()}</td>
      <td class="numeric ${row.owners_delta >= 0 ? 'pos' : 'neg'}">${row.owners_delta >= 0 ? '+' : ''}${row.owners_delta.toLocaleString()}</td>
      <td class="numeric ${(row.weight_delta_pct || 0) >= 0 ? 'pos' : 'neg'}">${row.weight_delta_pct === null ? '—' : `${row.weight_delta_pct >= 0 ? '+' : ''}${row.weight_delta_pct.toFixed(1)}%`}</td>
      <td class="numeric crowd-score">${formatNum(row.to_crowd_score)}</td>
    </tr>`;
  }).join('');

  updatePagination(data.pagination);
  els.resultsContainer.classList.add('active');
  els.exportContainer.classList.remove('fso-hidden');
}

function displayNewPositionResults(data) {
  els.resultsTitle.textContent =
    `New Positions — ${data.query_params.from} → ${data.query_params.to}`;

  els.tableHead.innerHTML = `<tr>
    <th>Rank</th>
    <th>Asset</th>
    <th>Size</th>
    <th>Type</th>
    <th class="numeric">Owners</th>
    <th class="numeric">Prev Owners</th>
    <th class="numeric">Total Weight</th>
    <th class="numeric">Tier</th>
  </tr>`;

  els.tableBody.innerHTML = data.data.map(row => `<tr>
    <td class="rank">${row.rank}</td>
    <td class="ticker">${escapeHtml(row.asset || 'Unknown')}</td>
    <td><span class="fso-badge size">${escapeHtml(row.size_bucket || '—')}</span></td>
    <td>${row.is_brand_new ? '<span class="fso-badge ok">brand new</span>'
                           : '<span class="fso-badge pending">re-entered</span>'}</td>
    <td class="numeric owners">${row.to_owners.toLocaleString()}</td>
    <td class="numeric">${row.from_owners.toLocaleString()}</td>
    <td class="numeric weight">${formatNum(row.to_weight)}</td>
    <td class="numeric">T${row.to_tier}</td>
  </tr>`).join('');

  updatePagination(data.pagination);
  els.resultsContainer.classList.add('active');
  els.exportContainer.classList.remove('fso-hidden');
}

function displaySizeResults(data) {
  els.resultsTitle.textContent =
    `Crowding by Size — ${els.yearSelect.value} Q${els.quarterSelect.value}`;

  els.tableHead.innerHTML = `<tr>
    <th>Size Bucket</th>
    <th class="numeric">Assets</th>
    <th class="numeric">Avg Owners</th>
    <th class="numeric">Total Weight</th>
    <th class="numeric">Avg Crowd Score</th>
    <th class="numeric">Max Crowd Score</th>
  </tr>`;

  els.tableBody.innerHTML = data.data.map(row => `<tr>
    <td class="ticker">${escapeHtml(row.size_bucket)}</td>
    <td class="numeric">${row.assets.toLocaleString()}</td>
    <td class="numeric owners">${row.avg_owners.toFixed(1)}</td>
    <td class="numeric weight">${formatNum(row.total_weight)}</td>
    <td class="numeric crowd-score">${formatNum(row.avg_crowd_score)}</td>
    <td class="numeric crowd-score">${formatNum(row.max_crowd_score)}</td>
  </tr>`).join('');

  els.paginationInfo.textContent = `${data.data.length} buckets`;
  els.pageInfo.textContent = '1 / 1';
  els.prevPageBtn.disabled = true;
  els.nextPageBtn.disabled = true;
  els.resultsContainer.classList.add('active');
  els.exportContainer.classList.remove('fso-hidden');
}

function displayPortfolioResults(data) {
  els.resultsTitle.textContent = `Portfolio — ${data.selected_manager?.name || ''}`;

  els.tableHead.innerHTML = `<tr>
    <th>Ticker</th><th>Name</th><th>CUSIP</th>
    <th class="numeric">Weight</th>
    <th class="numeric">Shares</th>
    <th class="numeric">Value</th>
  </tr>`;

  els.tableBody.innerHTML = data.data.map(row => `<tr>
    <td class="ticker">${escapeHtml(row.ticker || '—')}</td>
    <td>${escapeHtml(row.name || 'Unknown')}</td>
    <td style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:#6E7681;">${row.cusip}</td>
    <td class="numeric weight">${formatNum(row.weight)}</td>
    <td class="numeric">${row.shares ? row.shares.toLocaleString() : '—'}</td>
    <td class="numeric">${row.value ? formatCurrency(row.value) : '—'}</td>
  </tr>`).join('');

  updatePagination(data.pagination);
  els.resultsContainer.classList.add('active');
  els.exportContainer.classList.remove('fso-hidden');
}

function displayOwnershipResults(data) {
  els.resultsTitle.textContent = `Owners — ${data.selected_asset?.name || ''}`;

  els.tableHead.innerHTML = `<tr>
    <th>Manager</th>
    <th class="numeric">Weight</th>
  </tr>`;

  els.tableBody.innerHTML = data.data.map(row => `<tr>
    <td>${escapeHtml(row.name || 'Unknown')}</td>
    <td class="numeric weight">${formatNum(row.weight)}</td>
  </tr>`).join('');

  updatePagination(data.pagination);
  els.resultsContainer.classList.add('active');
  els.exportContainer.classList.remove('fso-hidden');
}

function displayAssetStats(stats) {
  els.assetStats.innerHTML = `
    <div class="fso-stat">
      <div class="fso-stat-value">${stats.total_owners.toLocaleString()}</div>
      <div class="fso-stat-label">Total Owners</div>
    </div>
    <div class="fso-stat">
      <div class="fso-stat-value">${formatNum(stats.total_weight)}</div>
      <div class="fso-stat-label">Total Weight</div>
    </div>
    <div class="fso-stat">
      <div class="fso-stat-value">${formatNum(stats.crowd_score)}</div>
      <div class="fso-stat-label">Crowd Score</div>
    </div>`;
  els.assetStats.classList.add('active');
}

// ══════════════════════════════════════════════════
//  PAGINATION
// ══════════════════════════════════════════════════
function updatePagination(pagination) {
  const { offset, limit, total, has_more } = pagination;
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages  = Math.max(1, Math.ceil(total / limit));

  els.paginationInfo.textContent = `${(offset + 1).toLocaleString()}–${Math.min(offset + limit, total).toLocaleString()} of ${total.toLocaleString()}`;
  els.pageInfo.textContent       = `${currentPage} / ${totalPages}`;
  els.prevPageBtn.disabled       = offset === 0;
  els.nextPageBtn.disabled       = !has_more;
}

function changePage(direction) {
  if (!currentPagination) return;
  const newOffset = currentPagination.offset + (direction * currentPagination.limit);
  if (newOffset < 0 || newOffset >= currentPagination.total) return;

  if      (currentQueryType === 'crowded')     { els.crowdedOffset.value = newOffset; searchCrowdedTrades(newOffset); }
  else if (currentQueryType === 'capitulation'){ els.capOffset.value = newOffset;     searchCapitulation(newOffset); }
  else if (currentQueryType === 'transitions') { searchTransitions(newOffset); }
  else if (currentQueryType === 'newpos')      { searchNewPositions(newOffset); }
  else if (currentQueryType === 'portfolio')   { searchPortfolio(newOffset); }
  else if (currentQueryType === 'ownership')   { searchAssetOwnership(newOffset); }
}

// ══════════════════════════════════════════════════
//  HELPERS
// ══════════════════════════════════════════════════
function formatNum(num) {
  if (num === null || num === undefined) return '—';
  const abs = Math.abs(num);
  if (abs >= 1e18) return `${(num/1e18).toFixed(2)}E`;
  if (abs >= 1e15) return `${(num/1e15).toFixed(2)}P`;
  if (abs >= 1e12) return `${(num/1e12).toFixed(2)}T`;
  if (abs >= 1e9)  return `${(num/1e9).toFixed(2)}B`;
  if (abs >= 1e6)  return `${(num/1e6).toFixed(2)}M`;
  if (abs >= 1e4)  return `${(num/1e3).toFixed(1)}K`;
  if (abs >= 100)  return num.toFixed(0);
  if (abs >= 1)    return num.toFixed(2);
  if (abs > 0)     return num.toExponential(2);
  return '0';
}

function formatCurrency(num) {
  if (num === null || num === undefined) return '—';
  if (num >= 1e12) return `$${(num/1e12).toFixed(2)}T`;
  if (num >= 1e9)  return `$${(num/1e9).toFixed(2)}B`;
  if (num >= 1e6)  return `$${(num/1e6).toFixed(2)}M`;
  if (num >= 1e3)  return `$${(num/1e3).toFixed(1)}K`;
  return `$${num.toFixed(2)}`;
}

function showResult(message, type = 'info') {
  els.resultMessage.textContent = message;
  els.resultMessage.className   = `fso-result active ${type}`;
  if (type === 'success' || type === 'info') {
    setTimeout(() => els.resultMessage.classList.remove('active'), 5000);
  }
}

function clearResults() {
  els.resultsContainer.classList.remove('active');
  els.exportContainer.classList.add('fso-hidden');
  els.resultMessage.classList.remove('active');
  els.selectedManager.classList.remove('active');
  els.selectedAsset.classList.remove('active');
  els.assetStats.classList.remove('active');
  els.trMatrixBox.classList.remove('active');
  currentData = []; currentPagination = null; currentQueryType = null;
}

function exportToCsv() {
  if (!currentData || currentData.length === 0) { showResult('No data to export', 'error'); return; }
  const headers = Object.keys(currentData[0]);
  let csv = headers.join(',') + '\n';
  currentData.forEach(row => {
    csv += headers.map(h => {
      const v = row[h];
      if (typeof v === 'string' && (v.includes(',') || v.includes('"')))
        return `"${v.replace(/"/g,'""')}"`;
      return v ?? '';
    }).join(',') + '\n';
  });
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `${currentQueryType}_${els.yearSelect.value}_Q${els.quarterSelect.value}.csv`;
  link.style.display = 'none';
  document.body.appendChild(link); link.click(); document.body.removeChild(link);
  showResult(`Exported ${currentData.length} rows`, 'success');
}

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const d = document.createElement('div'); d.textContent = text; return d.innerHTML;
}

// ── Boot ──
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
