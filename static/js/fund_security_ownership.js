// fund_security_ownership.js — Bias dark theme
// All original logic preserved. Period selector moved to header.

const BASE_URL = '/fund_security_ownership';

const els = {
  // Period
  yearSelect:       document.getElementById('yearSelect'),
  quarterSelect:    document.getElementById('quarterSelect'),
  periodStatus:     document.getElementById('periodStatus'),

  // Tabs
  tabs:             document.querySelectorAll('.fso-tab'),
  tabContents:      document.querySelectorAll('.fso-tab-content'),

  // Crowded
  crowdedOffset:    document.getElementById('crowdedOffset'),
  crowdedMinScore:  document.getElementById('crowdedMinScore'),
  crowdedLimit:     document.getElementById('crowdedLimit'),
  crowdedSearchBtn: document.getElementById('crowdedSearchBtn'),

  // Capitulation
  capMinOwners:     document.getElementById('capMinOwners'),
  capOffset:        document.getElementById('capOffset'),
  capLimit:         document.getElementById('capLimit'),
  capSearchBtn:     document.getElementById('capSearchBtn'),

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

// ══════════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════════
function init() {
  loadAvailablePeriods();
  setupTabListeners();
  setupSearchListeners();
  setupPaginationListeners();
  setupSuggestionListeners();
  setupExportListener();
}

// ══════════════════════════════════════════════════
//  PERIODS
// ══════════════════════════════════════════════════
async function loadAvailablePeriods() {
  try {
    const response = await fetch(`${BASE_URL}/available_periods`);
    const data = await response.json();

    if (data.status === 'ok' && data.periods.length > 0) {
      const years = [...new Set(data.periods.map(p => p.year))].sort((a, b) => b - a);

      els.yearSelect.innerHTML = '<option value="" disabled selected>Year</option>';
      years.forEach(year => {
        const opt = document.createElement('option');
        opt.value = opt.textContent = year;
        els.yearSelect.appendChild(opt);
      });

      if (data.periods.length > 0) {
        els.yearSelect.value    = data.periods[0].year;
        els.quarterSelect.value = data.periods[0].quarter;
        els.periodStatus.textContent = `✓ ${data.periods.length} periods`;
      }
    }
  } catch (err) {
    console.error('Failed to load periods:', err);
    els.periodStatus.textContent  = '✗ Error';
    els.periodStatus.style.color  = '#F85149';
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
    });
  });
}

// ══════════════════════════════════════════════════
//  SEARCH LISTENERS
// ══════════════════════════════════════════════════
function setupSearchListeners() {
  els.crowdedSearchBtn.addEventListener('click',  () => searchCrowdedTrades());
  els.capSearchBtn.addEventListener('click',      () => searchCapitulation());
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
  const totalPages  = Math.ceil(total / limit);

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
  if (!text) return '';
  const d = document.createElement('div'); d.textContent = text; return d.innerHTML;
}

// ── Boot ──
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}