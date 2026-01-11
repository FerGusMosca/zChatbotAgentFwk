// document_tag_indexer.js - Robust version with full error handling + spinner

const BASE_URL = '/document_tag_indexer';

// DOM elements cache
const els = {
  modeOld: document.getElementById('modeOld'),
  modeNew: document.getElementById('modeNew'),
  newSection: document.getElementById('newRunSection'),
  oldSection: document.getElementById('oldRunsSection'),
  portfolioSelect: document.getElementById('portfolioSelect'),
  sourceSelect: document.getElementById('sourceSelect'),
  quarterSelect: document.getElementById('quarterSelect'),
  tagModelSelect: document.getElementById('tagModelSelect'),
  tagNameInput: document.getElementById('tagNameInput'),
  docTypeSelect: document.getElementById('docTypeSelect'),
  tagTypeSelect: document.getElementById('tagTypeSelect'),
  tagContent: document.getElementById('tagContent'),
  form: document.getElementById('newRunForm'),
  resultMsg: document.getElementById('resultMessage'),
  createBtn: document.getElementById('createRunBtn') // 🔄 spinner button
};

// Toggle between modes
function toggleMode() {
  const isNewMode = els.modeNew.checked;
  els.newSection.classList.toggle('dti-hidden', !isNewMode);
  els.oldSection.classList.toggle('dti-hidden', isNewMode);
}

// Show/hide quarter select based on source
function handleSourceChange() {
  const isQ10 = els.sourceSelect.value === 'q10';
  els.quarterSelect.classList.toggle('dti-hidden', !isQ10);

  if (!isQ10) els.quarterSelect.value = '';
  els.quarterSelect.required = isQ10;
}

// Load dropdown options from API
async function loadDropdownData() {
  try {
    const responses = await Promise.all([
      fetch(`${BASE_URL}/portfolios`),
      fetch(`${BASE_URL}/sources`),
      fetch(`${BASE_URL}/tag_models`),
      fetch(`${BASE_URL}/doc_types`),
      fetch(`${BASE_URL}/tag_types`)
    ]);

    const jsons = await Promise.all(responses.map(async res => {
      if (!res.ok) throw new Error(`HTTP ${res.status} on ${res.url}`);
      return res.json();
    }));

    const [portfolios, sources, models, docTypes, tagTypes] = jsons;

    (portfolios.portfolios || []).forEach(p => {
      const opt = document.createElement('option');
      opt.value = opt.textContent = p;
      els.portfolioSelect.appendChild(opt);
    });
    if (portfolios.error) throw new Error(portfolios.error);

    (sources.sources || []).forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.code;
      opt.textContent = s.name;
      els.sourceSelect.appendChild(opt);
    });
    if (sources.error) throw new Error(sources.error);

    (models.models || []).forEach(m => {
      const opt = document.createElement('option');
      opt.value = opt.textContent = m;
      els.tagModelSelect.appendChild(opt);
    });
    if (models.error) throw new Error(models.error);

    (docTypes.doc_types || []).forEach(dt => {
      const opt = document.createElement('option');
      opt.value = dt.code;
      opt.textContent = dt.name;
      els.docTypeSelect.appendChild(opt);
    });
    if (docTypes.error) throw new Error(docTypes.error);

    (tagTypes.tag_types || []).forEach(tt => {
      const opt = document.createElement('option');
      opt.value = tt.code;
      opt.textContent = tt.name;
      els.tagTypeSelect.appendChild(opt);
    });
    if (tagTypes.error) throw new Error(tagTypes.error);

  } catch (err) {
    console.error('Dropdown load failed:', err);
    showResult(err.message || err, 'error');
  }
}

function showResult(message, status) {
  els.resultMsg.textContent = message;
  els.resultMsg.className =
    status === 'error'
      ? 'dti-result dti-error dti-visible'
      : 'dti-result dti-success dti-visible';
}

// Handle form submission + spinner
async function handleFormSubmit(e) {
  e.preventDefault();

  const formData = new FormData(els.form);
  if (els.sourceSelect.value !== 'q10') formData.delete('quarter');

  els.createBtn.classList.add('loading'); // 🔄 SHOW SPINNER

  try {
    const response = await fetch(`${BASE_URL}/create_run`, {
      method: 'POST',
      body: formData
    });

    const data = await response.json();

    if (!response.ok || data.status !== 'ok') {
      throw new Error(data.message || data.error || `HTTP ${response.status}`);
    }

    showResult(`✓ Run created: ${data.message}`, 'success');

  } catch (err) {
    console.error('Form submit failed:', err);
    showResult(`Submission error: ${err.message || 'Please try again'}`, 'error');

  } finally {
    els.createBtn.classList.remove('loading'); // ✅ HIDE SPINNER
  }
}

// Initialize
function init() {
  els.modeOld.addEventListener('change', toggleMode);
  els.modeNew.addEventListener('change', toggleMode);
  els.sourceSelect.addEventListener('change', handleSourceChange);
  els.form.addEventListener('submit', handleFormSubmit);

  loadDropdownData();
  toggleMode();
  handleSourceChange();
}

// Start app
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
