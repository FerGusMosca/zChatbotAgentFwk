// deep_company_analysis.js — Bias dark theme
// All original logic preserved. Added: status bar, improved result rendering.

const BASE_URL = '/deep_company_analysis';

const els = {
  form:                       document.getElementById('analysisForm'),
  symbolInput:                document.getElementById('symbolInput'),
  docTypeSelect:              document.getElementById('docTypeSelect'),
  yearInput:                  document.getElementById('yearInput'),
  quarterSelect:              document.getElementById('quarterSelect'),
  quarterPlaceholder:         document.getElementById('quarterPlaceholder'),
  freeTextRow:                document.getElementById('freeTextRow'),
  freeTextArea:               document.getElementById('freeTextArea'),
  sentimentBtn:               document.getElementById('sentimentBtn'),
  topicsBtn:                  document.getElementById('topicsBtn'),
  freeAnalysisBtn:            document.getElementById('freeAnalysisBtn'),
  freeAnalysisPromptSection:  document.getElementById('freeAnalysisPromptSection'),
  freeAnalysisPrompt:         document.getElementById('freeAnalysisPrompt'),
  resultMessage:              document.getElementById('resultMessage'),
  topicModal:                 document.getElementById('topicModal'),
  closeTopicModal:            document.getElementById('closeTopicModal'),
  tagNameInput:               document.getElementById('tagNameInput'),
  topicsInput:                document.getElementById('topicsInput'),
  submitTopics:               document.getElementById('submitTopics'),
  topicProgressContainer:     document.getElementById('topicProgressContainer'),
  topicProgressMessages:      document.getElementById('topicProgressMessages'),
  uploadFileBtn:              document.getElementById('uploadFileBtn'),
  fileUploadInput:            document.getElementById('fileUploadInput'),
  uploadedFileName:           document.getElementById('uploadedFileName'),
  clearFileBtn:               document.getElementById('clearFileBtn'),
  promptSelector:             document.getElementById('promptSelector'),
  resultsModal:               document.getElementById('resultsModal'),
  resultsModalTitle:          document.getElementById('resultsModalTitle'),
  resultsModalContent:        document.getElementById('resultsModalContent'),
  closeResultsModal:          document.getElementById('closeResultsModal'),
  k8Row:                      document.getElementById('k8Row'),
  downloadK8Btn:              document.getElementById('downloadK8Btn'),
  k8Status:                   document.getElementById('k8Status'),
  k8TextArea:                 document.getElementById('k8TextArea'),
  f4Row:                      document.getElementById('f4Row'),
  downloadF4Btn:              document.getElementById('downloadF4Btn'),
  f4Status:                   document.getElementById('f4Status'),
  f4TextArea:                 document.getElementById('f4TextArea'),
  statusDot:                  document.getElementById('statusDot'),
  statusText:                 document.getElementById('statusText'),
};

// ── State ──
let currentSymbol = null;
let symbolValidated = false;
let validationDebounceTimer = null;

// ══════════════════════════════════════════════════
//  STATUS BAR
// ══════════════════════════════════════════════════
function setStatus(message, type = 'idle') {
  // type: idle | info | success | error
  els.statusDot.className = 'dca-status-dot' + (type !== 'idle' ? ` ${type}` : '');
  els.statusText.textContent = message;
}

// ══════════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════════
function init() {
  setupEventListeners();
  setupFileUploadListeners();
  setupPromptSelectorListener();
  setupResultsModalListeners();
  setAnalysisButtonsEnabled(false);
  els.downloadK8Btn.addEventListener('click', handleDownloadK8);
  els.downloadF4Btn.addEventListener('click', handleDownloadF4);
  setStatus('Enter a symbol to begin');
}

function setAnalysisButtonsEnabled(enabled) {
  els.sentimentBtn.disabled = !enabled;
  els.topicsBtn.disabled    = !enabled;
  els.freeAnalysisBtn.disabled = !enabled;
}

// ══════════════════════════════════════════════════
//  EVENT LISTENERS
// ══════════════════════════════════════════════════
function setupEventListeners() {
  els.docTypeSelect.addEventListener('change', handleDocTypeChange);
  els.symbolInput.addEventListener('input', handleSymbolInput);
  els.symbolInput.addEventListener('blur', validateSymbol);
  els.sentimentBtn.addEventListener('click', () => handleAnalysis('sentiment'));
  els.topicsBtn.addEventListener('click', openTopicModal);
  els.freeAnalysisBtn.addEventListener('click', () => handleAnalysis('free'));
  els.closeTopicModal.addEventListener('click', closeTopicModal);
  els.topicModal.addEventListener('click', e => { if (e.target === els.topicModal) closeTopicModal(); });
  els.submitTopics.addEventListener('click', handleTopicAnalysis);
}

function handleSymbolInput() {
  clearTimeout(validationDebounceTimer);
  const symbol = els.symbolInput.value.trim();
  if (!symbol) {
    symbolValidated = false;
    currentSymbol = null;
    setAnalysisButtonsEnabled(false);
    setStatus('Enter a symbol to begin');
    return;
  }
  setStatus('Validating…', 'info');
  validationDebounceTimer = setTimeout(validateSymbol, 500);
}

function setupResultsModalListeners() {
  els.closeResultsModal.addEventListener('click', closeResultsModal);
  els.resultsModal.addEventListener('click', e => { if (e.target === els.resultsModal) closeResultsModal(); });
}

function showResultsModal(title, content) {
  els.resultsModalTitle.textContent = title;
  els.resultsModalContent.innerHTML = content;
  els.resultsModal.classList.remove('dca-hidden');
}

function closeResultsModal() {
  els.resultsModal.classList.add('dca-hidden');
}

// ══════════════════════════════════════════════════
//  FILE UPLOAD
// ══════════════════════════════════════════════════
function setupFileUploadListeners() {
  els.uploadFileBtn.addEventListener('click', () => els.fileUploadInput.click());
  els.fileUploadInput.addEventListener('change', handleFileUpload);
  els.clearFileBtn.addEventListener('click', clearUploadedFile);
}

async function handleFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  els.uploadedFileName.textContent = file.name;
  els.clearFileBtn.classList.remove('dca-hidden');
  try {
    const ext = file.name.split('.').pop().toLowerCase();
    let text = '';
    if (ext === 'txt') text = await readTextFile(file);
    else if (ext === 'pdf') text = await extractTextFromPDF(file);
    else if (ext === 'doc' || ext === 'docx') text = await extractTextFromWord(file);
    else { showResult('Unsupported file type. Use .txt, .pdf, .doc, or .docx', 'error', false); clearUploadedFile(); return; }
    els.freeTextArea.value = text;
    setStatus(`Loaded ${file.name} — ${text.length.toLocaleString()} chars`, 'success');
  } catch (err) {
    showResult(`Error reading file: ${err.message}`, 'error', false);
    clearUploadedFile();
  }
}

function clearUploadedFile() {
  els.fileUploadInput.value = '';
  els.uploadedFileName.textContent = '';
  els.clearFileBtn.classList.add('dca-hidden');
  els.freeTextArea.value = '';
}

function readTextFile(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = e => res(e.target.result);
    r.onerror = () => rej(new Error('Failed to read file'));
    r.readAsText(file);
  });
}

async function extractTextFromPDF(file) {
  if (typeof pdfjsLib === 'undefined') throw new Error('PDF.js not loaded');
  const buf = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
  let out = '';
  for (let i = 1; i <= pdf.numPages; i++) {
    const pg = await pdf.getPage(i);
    const tc = await pg.getTextContent();
    out += tc.items.map(x => x.str).join(' ') + '\n\n';
  }
  return out.trim();
}

async function extractTextFromWord(file) {
  if (typeof mammoth === 'undefined') throw new Error('Mammoth.js not loaded');
  const buf = await file.arrayBuffer();
  const result = await mammoth.extractRawText({ arrayBuffer: buf });
  return result.value;
}

// ══════════════════════════════════════════════════
//  PROMPT SELECTOR
// ══════════════════════════════════════════════════
function setupPromptSelectorListener() {
  els.promptSelector.addEventListener('change', handlePromptSelection);
}

async function handlePromptSelection() {
  const selected = els.promptSelector.value;
  if (!selected) return;
  const files = {
    standard_earnings:  '/static/prompts/standard_earnings_transcripts.txt',
    k8_events_analysis: '/static/prompts/k8_events_analysis.txt',
    f4_insider_analysis:'/static/prompts/f4_insider_analysis.txt'
  };
  try {
    const resp = await fetch(files[selected]);
    if (!resp.ok) throw new Error(resp.statusText);
    els.freeAnalysisPrompt.value = await resp.text();
    setStatus(`Loaded: ${els.promptSelector.options[els.promptSelector.selectedIndex].text}`, 'success');
  } catch (err) {
    showResult(`Error loading prompt: ${err.message}`, 'error', false);
  }
}

// ══════════════════════════════════════════════════
//  DOC TYPE CHANGE
// ══════════════════════════════════════════════════
function handleDocTypeChange() {
  const dt = els.docTypeSelect.value;

  els.freeTextRow.classList.add('dca-hidden');
  els.k8Row.classList.add('dca-hidden');
  els.f4Row.classList.add('dca-hidden');
  els.quarterSelect.classList.add('dca-hidden');
  els.quarterPlaceholder?.classList.remove('dca-hidden');

  els.freeAnalysisBtn.classList.add('dca-hidden');
  els.freeAnalysisPromptSection.classList.add('dca-hidden');
  els.sentimentBtn.classList.remove('dca-hidden');
  els.topicsBtn.classList.remove('dca-hidden');

  if (dt === '10Q') {
    els.quarterSelect.classList.remove('dca-hidden');
    els.quarterPlaceholder?.classList.add('dca-hidden');
  } else if (dt === 'FREE_TEXT') {
    els.freeTextRow.classList.remove('dca-hidden');
    els.freeAnalysisBtn.classList.remove('dca-hidden');
    els.freeAnalysisPromptSection.classList.remove('dca-hidden');
    els.sentimentBtn.classList.add('dca-hidden');
    els.topicsBtn.classList.add('dca-hidden');
  } else if (dt === '8K') {
    els.k8Row.classList.remove('dca-hidden');
    els.freeAnalysisBtn.classList.remove('dca-hidden');
    els.freeAnalysisPromptSection.classList.remove('dca-hidden');
    els.sentimentBtn.classList.add('dca-hidden');
    els.topicsBtn.classList.add('dca-hidden');
  } else if (dt === '4F') {
    els.f4Row.classList.remove('dca-hidden');
    els.freeAnalysisBtn.classList.remove('dca-hidden');
    els.freeAnalysisPromptSection.classList.remove('dca-hidden');
    els.sentimentBtn.classList.add('dca-hidden');
    els.topicsBtn.classList.add('dca-hidden');
  }
}

// ══════════════════════════════════════════════════
//  SYMBOL VALIDATION
// ══════════════════════════════════════════════════
async function validateSymbol() {
  const symbol = els.symbolInput.value.trim().toUpperCase();
  if (!symbol) { setAnalysisButtonsEnabled(false); return; }
  try {
    const fd = new FormData();
    fd.append('symbol', symbol);
    const resp = await fetch(`${BASE_URL}/validate_symbol`, { method: 'POST', body: fd });
    const data = await resp.json();
    if (data.status === 'ok' && data.valid) {
      currentSymbol = data.symbol;
      symbolValidated = true;
      setAnalysisButtonsEnabled(true);
      setStatus(`✓ ${data.symbol} — ${data.name}`, 'success');
      showResult(`✓ Symbol ${data.symbol} validated: ${data.name}`, 'success', false);
    } else {
      symbolValidated = false; currentSymbol = null;
      setAnalysisButtonsEnabled(false);
      setStatus(`Symbol ${symbol} not found`, 'error');
      showResult(`✗ Symbol ${symbol} not found in database`, 'error', false);
    }
  } catch (err) {
    symbolValidated = false; currentSymbol = null;
    setAnalysisButtonsEnabled(false);
    setStatus(`Validation error`, 'error');
    showResult(`Error validating symbol: ${err.message}`, 'error', false);
  }
}

// ══════════════════════════════════════════════════
//  TOPIC MODAL
// ══════════════════════════════════════════════════
function openTopicModal() {
  if (!els.form.checkValidity()) { els.form.reportValidity(); return; }
  if (!symbolValidated) { setStatus('Validate a symbol first', 'error'); els.symbolInput.focus(); return; }
  els.tagNameInput.value = '';
  els.topicsInput.value = '';
  els.topicProgressContainer.classList.add('dca-hidden');
  els.topicProgressMessages.innerHTML = '';
  els.topicModal.classList.remove('dca-hidden');
}

function closeTopicModal() { els.topicModal.classList.add('dca-hidden'); }

function addProgressMessage(msg) {
  const div = document.createElement('div');
  div.style.marginTop = '3px';
  div.textContent = msg;
  els.topicProgressMessages.appendChild(div);
  els.topicProgressContainer.scrollTop = els.topicProgressContainer.scrollHeight;
}

async function handleTopicAnalysis() {
  const tagName   = els.tagNameInput.value.trim();
  const topicsText = els.topicsInput.value.trim();
  if (!tagName)    { alert('Please enter a tag name'); els.tagNameInput.focus(); return; }
  if (!topicsText) { alert('Please enter at least one topic'); els.topicsInput.focus(); return; }

  const btn = els.submitTopics;
  btn.classList.add('loading'); btn.disabled = true;
  els.topicProgressContainer.classList.remove('dca-hidden');
  els.topicProgressMessages.innerHTML = '<div style="color:#58A6FF;">🚀 Starting analysis…</div>';

  try {
    const symbol  = els.symbolInput.value.trim().toUpperCase();
    const docType = els.docTypeSelect.value;
    const year    = els.yearInput.value;
    const quarter = els.quarterSelect.value || null;
    const freeText = els.freeTextArea.value || null;

    const fd = new FormData();
    fd.append('symbol', symbol); fd.append('doc_type', docType);
    fd.append('year', year); fd.append('tag_name', tagName);
    fd.append('topic_list', topicsText);
    if (quarter)   fd.append('quarter', quarter);
    if (freeText)  fd.append('free_text', freeText);

    const response = await fetch(`${BASE_URL}/analyze_topics`, { method: 'POST', body: fd });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const reader  = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', finalData = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop();
      for (const ev of events) {
        if (!ev.startsWith('data: ')) continue;
        const json = JSON.parse(ev.slice(6));
        if (json.type === 'progress') addProgressMessage(json.message);
        else if (json.type === 'result') finalData = json.data;
        else if (json.type === 'error') throw new Error(json.message);
      }
    }

    if (!finalData) throw new Error('No result received from server');
    closeTopicModal();
    displayResults(finalData, 'topics');

  } catch (err) {
    console.error('Topic analysis failed:', err);
    els.topicProgressMessages.innerHTML += `<div style="color:#F85149;">❌ ${err.message}</div>`;
    alert(`Analysis error: ${err.message}`);
  } finally {
    btn.classList.remove('loading'); btn.disabled = false;
  }
}

// ══════════════════════════════════════════════════
//  MAIN ANALYSIS HANDLER
// ══════════════════════════════════════════════════
async function handleAnalysis(analysisType) {
  if (!els.form.checkValidity()) { els.form.reportValidity(); return; }
  if (!symbolValidated) { setStatus('Validate a symbol first', 'error'); els.symbolInput.focus(); return; }

  const docType = els.docTypeSelect.value;
  let textToAnalyze = '';
  if (docType === '8K')        textToAnalyze = els.k8TextArea.value.trim();
  else if (docType === '4F')   textToAnalyze = els.f4TextArea.value.trim();
  else if (docType === 'FREE_TEXT') textToAnalyze = els.freeTextArea.value.trim();

  const requiresLocalText = ['8K', '4F', 'FREE_TEXT'].includes(docType);
  if (requiresLocalText && !textToAnalyze) {
    setStatus(`No content for ${docType} — download or paste first`, 'error');
    return;
  }

  const btn = (analysisType === 'sentiment') ? els.sentimentBtn : els.freeAnalysisBtn;
  const promptValue = els.freeAnalysisPrompt.value.trim();

  if (analysisType === 'free' && !promptValue) {
    setStatus('Enter a prompt for free analysis', 'error');
    els.freeAnalysisPrompt.focus(); return;
  }

  btn.classList.add('loading'); btn.disabled = true;
  setStatus('Running analysis…', 'info');

  try {
    const fd = new FormData();
    fd.append('symbol', els.symbolInput.value.trim().toUpperCase());
    fd.append('doc_type', docType);
    fd.append('year', els.yearInput.value);
    if (textToAnalyze) fd.append('free_text', textToAnalyze);
    if (els.quarterSelect.value) fd.append('quarter', els.quarterSelect.value);

    let endpoint = `${BASE_URL}/analyze_sentiment`;
    if (analysisType === 'free') {
      endpoint = `${BASE_URL}/free_analysis`;
      fd.append('prompt', promptValue);
    }

    const response = await fetch(endpoint, { method: 'POST', body: fd });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || `Server Error: ${response.status}`);

    displayResults(data, analysisType);
    setStatus('Analysis completed', 'success');

  } catch (err) {
    console.error('Analysis failed:', err);
    setStatus(`Error: ${err.message}`, 'error');
    showResult(`Analysis error: ${err.message}`, 'error', true);
  } finally {
    btn.classList.remove('loading'); btn.disabled = false;
  }
}

// ══════════════════════════════════════════════════
//  DISPLAY RESULTS
// ══════════════════════════════════════════════════
function displayResults(data, analysisType) {
  let html = '';

  // ── SENTIMENT ──
  if (analysisType === 'sentiment') {
    if (data.status === 'failed' || data.status === 'error') {
      html = errorBlock('Sentiment Analysis Failed', data.message, data.error_type);
    } else if (data.status === 'completed' && data.analysis) {
      const a = data.analysis || {};
      const m = a.metrics || {};
      const topPos = a.top_positive || [];
      const topNeg = a.top_negative || [];

      html = `
        <div class="dca-result-display">
          <div style="display:flex;gap:8px;margin-bottom:18px;flex-wrap:wrap;">
            ${metaTag(data.symbol || '—')}
            ${metaTag(data.year || '—')}
            ${metaTag(data.period || '—')}
          </div>

          <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:20px;">
            ${metricCard('MD&A Sentiment', scoreValue(m.mdna_sentiment || 0, 3), toneColor(m.mdna_sentiment || 0))}
            ${metricCard('Financial Sentences', m.financial_sentences || 0, '#E6EDF3')}
            ${metricCard('Forward-Looking', pct(m.forward_ratio || 0), (m.forward_ratio||0)>0.3?'#3FB950':'#8B949E')}
            ${metricCard('Hedging Language', pct(m.hedge_ratio || 0), (m.hedge_ratio||0)>0.2?'#F85149':'#8B949E')}
          </div>

          ${topPos.length ? `
            <div style="margin-bottom:16px;">
              <div class="dca-section-label" style="color:#3FB950;margin-bottom:8px;">✅ Most Positive</div>
              <div class="dca-scroll-inner">
                ${topPos.map(x => `
                  <div class="dca-sentiment-card positive">
                    ${escapeHtml(x.sent)}
                    <div class="dca-sentiment-score">Score: ${x.score.toFixed(3)}</div>
                  </div>`).join('')}
              </div>
            </div>` : ''}

          ${topNeg.length ? `
            <div>
              <div class="dca-section-label" style="color:#F85149;margin-bottom:8px;">⚠️ Most Negative</div>
              <div class="dca-scroll-inner">
                ${topNeg.map(x => `
                  <div class="dca-sentiment-card negative">
                    ${escapeHtml(x.sent)}
                    <div class="dca-sentiment-score">Score: ${x.score.toFixed(3)}</div>
                  </div>`).join('')}
              </div>
            </div>` : ''}
        </div>`;
    } else {
      html = unexpectedBlock(data);
    }

  // ── TOPICS ──
  } else if (analysisType === 'topics') {
    if (data.status === 'failed' || data.status === 'error') {
      html = errorBlock('Topic Analysis Failed', data.message, data.error_type);
    } else if (data.status === 'completed' && data.analysis) {
      const topics = (data.analysis || {}).topics || {};
      const keys = Object.keys(topics);
      html = `
        <div class="dca-result-display">
          <div style="display:flex;gap:8px;margin-bottom:18px;flex-wrap:wrap;">
            ${metaTag(data.symbol||'—')}${metaTag(data.year||'—')}
            ${metaTag(`${keys.length} topic${keys.length!==1?'s':''}`)}
          </div>
          ${keys.map(k => {
            const t = topics[k];
            const matches = t.matches || [];
            return `
              <div class="dca-topic-card">
                <h5>${k.replace(/_/g,' ').toUpperCase()}</h5>
                <div class="dca-topic-meta">
                  Top score: <span style="color:#3FB950;">${((t.top_score||0)*100).toFixed(1)}%</span>
                  &nbsp;·&nbsp; Matches: <span style="color:#58A6FF;">${matches.length}</span>
                </div>
                ${t.summary ? `<div style="color:#6E7681;font-size:12px;font-style:italic;margin-bottom:12px;padding:10px;background:#080C10;border-radius:6px;">${escapeHtml(t.summary)}</div>` : ''}
                ${matches.length ? `
                  <div class="dca-scroll-inner">
                    ${matches.map((m,i) => `
                      <div class="dca-match-item" style="border-left-color:${scoreColor(m.score)};">
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                          <span style="color:#484F58;font-family:'IBM Plex Mono',monospace;font-size:11px;">Match #${i+1}</span>
                          <span style="color:${scoreColor(m.score)};font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;">${(m.score*100).toFixed(1)}%</span>
                        </div>
                        ${m.matched_phrase ? `<div style="color:#3FB950;font-size:12px;margin-bottom:6px;padding:6px 8px;background:#0A1F10;border-radius:4px;">"${escapeHtml(m.matched_phrase)}"</div>` : ''}
                        <div style="font-size:13px;line-height:1.55;">${escapeHtml((m.chunk_text||'').replace(/<[^>]*>/g,''))}</div>
                      </div>`).join('')}
                  </div>` : ''}
              </div>`;
          }).join('')}
        </div>`;
    } else {
      html = unexpectedBlock(data);
    }

  // ── FREE ──
  } else if (analysisType === 'free') {
    if (data.status === 'error') {
      html = errorBlock('Free Analysis Failed', data.message);
    } else if (data.status === 'completed' && data.analysis?.response) {
      html = `
        <div class="dca-result-display">
          <div style="display:flex;gap:8px;margin-bottom:16px;">
            ${metaTag(data.symbol||'—')}
          </div>
          <div class="dca-free-response">${escapeHtml(data.analysis.response)}</div>
        </div>`;
    } else {
      html = unexpectedBlock(data);
    }
  }

  const titles = { sentiment: '📊 Sentiment Analysis', topics: '🏷️ Topic Analysis', free: '🤖 Free Analysis' };
  showResultsModal(titles[analysisType] || 'Results', html);
  showResult('✓ Analysis completed', 'success', true);
}

// ── Render helpers ──
function metaTag(v) {
  return `<span style="background:#161B22;border:1px solid #21262D;border-radius:5px;padding:3px 9px;font-family:'IBM Plex Mono',monospace;font-size:11px;color:#6E7681;">${escapeHtml(String(v))}</span>`;
}

function metricCard(label, value, color) {
  return `
    <div style="background:#161B22;border:1px solid #21262D;border-radius:8px;padding:12px 14px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#484F58;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">${label}</div>
      <div style="font-size:18px;font-weight:600;color:${color};font-family:'IBM Plex Mono',monospace;">${value}</div>
    </div>`;
}

function errorBlock(title, message, errorType) {
  return `
    <div class="dca-result-display">
      <h4 style="color:#F85149;">❌ ${escapeHtml(title)}</h4>
      <p style="color:#C9D1D9;font-size:13px;">${escapeHtml(message || 'Unknown error')}</p>
      ${errorType ? `<p style="color:#484F58;font-size:12px;font-family:'IBM Plex Mono',monospace;">${escapeHtml(errorType)}</p>` : ''}
    </div>`;
}

function unexpectedBlock(data) {
  return `
    <div class="dca-result-display">
      <h4 style="color:#9E6A03;">⚠️ Unexpected Response</h4>
      <pre style="background:#161B22;padding:12px;border-radius:6px;font-size:12px;overflow-x:auto;color:#C9D1D9;font-family:'IBM Plex Mono',monospace;">${escapeHtml(JSON.stringify(data,null,2))}</pre>
    </div>`;
}

function scoreValue(v, decimals) { return v.toFixed(decimals); }
function pct(v) { return `${(v*100).toFixed(1)}%`; }
function toneColor(s) { return s>0.7?'#3FB950':s>0.4?'#D29922':'#F85149'; }
function scoreColor(s) { return s>0.6?'#3FB950':s>0.4?'#D29922':'#F85149'; }

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

// ══════════════════════════════════════════════════
//  LEGACY showResult (kept for compat)
// ══════════════════════════════════════════════════
function showResult(message, type = 'info', autoHide = true) {
  if (!message) { els.resultMessage.style.display = 'none'; return; }
  const colors = { success:'#3FB950', error:'#F85149', info:'#58A6FF', warning:'#D29922' };
  const icons  = { success:'✓', error:'✗', info:'ℹ', warning:'⚠' };
  els.resultMessage.style.color   = colors[type] || colors.info;
  els.resultMessage.textContent   = `${icons[type]||''} ${message}`;
  els.resultMessage.style.display = 'block';
  if (autoHide && (type==='info'||type==='success')) {
    setTimeout(() => { els.resultMessage.style.display = 'none'; }, 5000);
  }
}

// ══════════════════════════════════════════════════
//  SEC DOWNLOAD — generic + specific handlers
// ══════════════════════════════════════════════════
async function handleSecReportDownload({ endpoint, reportType, btn, status, textArea }) {
  const symbol = els.symbolInput.value.trim().toUpperCase();
  const year   = els.yearInput.value.trim();
  if (!symbol) { setStatus('Enter a symbol first', 'error'); return; }
  if (!year)   { setStatus('Enter a year first', 'error'); return; }

  const orig = btn.innerHTML;
  btn.disabled = true; btn.innerHTML = '⏳ Downloading…';
  status.textContent = 'Connecting…';
  setStatus(`Downloading ${reportType}…`, 'info');
  textArea.value = '';

  try {
    const fd = new FormData();
    fd.append('symbol', symbol); fd.append('year', year);
    const resp = await fetch(`${BASE_URL}${endpoint}`, { method: 'POST', body: fd });
    const data = await resp.json();

    if (data.status === 'ok' || data.status === 'completed') {
      textArea.value = data.content || data.text || JSON.stringify(data.result, null, 2);
      status.textContent = `✓ Downloaded for ${symbol} (${year})`;
      setStatus(`${reportType} downloaded for ${symbol}`, 'success');
    } else {
      status.textContent = `✗ ${data.message || 'Download failed'}`;
      setStatus(data.message || 'Download failed', 'error');
    }
  } catch (err) {
    status.textContent = `✗ ${err.message}`;
    setStatus(`Error: ${err.message}`, 'error');
  } finally {
    btn.disabled = false; btn.innerHTML = orig;
  }
}

async function handleDownloadK8() {
  await handleSecReportDownload({ endpoint:'/download_k8', reportType:'8-K', btn:els.downloadK8Btn, status:els.k8Status, textArea:els.k8TextArea });
}
async function handleDownloadF4() {
  await handleSecReportDownload({ endpoint:'/download_f4', reportType:'Form 4', btn:els.downloadF4Btn, status:els.f4Status, textArea:els.f4TextArea });
}

// ── Boot ──
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}