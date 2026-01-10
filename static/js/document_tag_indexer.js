// document_tag_indexer.js - Robust version with full error handling

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
  tagContent: document.getElementById('tagContent'),
  form: document.getElementById('newRunForm'),
  resultMsg: document.getElementById('resultMessage')
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

// Load dropdown options from API with robust error handling
async function loadDropdownData() {
  try {
    const responses = await Promise.all([
      fetch(`${BASE_URL}/portfolios`),
      fetch(`${BASE_URL}/sources`),
      fetch(`${BASE_URL}/tag_models`),
      fetch(`${BASE_URL}/doc_types`)
    ]);

    const jsons = await Promise.all(responses.map(async res => {
      if (!res.ok) throw new Error(`HTTP ${res.status} on ${res.url}`);
      return res.json();
    }));

    const [portfolios, sources, models, docTypes] = jsons;

    // Populate portfolios
    (portfolios.portfolios || []).forEach(p => {
      const opt = document.createElement('option');
      opt.value = opt.textContent = p;
      els.portfolioSelect.appendChild(opt);
    });

   if (portfolios.error)
        throw new Error(portfolios.error);

    // Populate sources
    (sources.sources || []).forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.code;
          opt.textContent = s.name;
          els.sourceSelect.appendChild(opt);
        });

    if (sources.error)
        throw new Error(sources.error);

    // Populate tag models
    (models.models || []).forEach(m => {

      const opt = document.createElement('option');
      opt.value = opt.textContent = m;
      els.tagModelSelect.appendChild(opt);
    });

    if (models.error)
        throw new Error(models.error);

    // Populate doc types
    (docTypes.doc_types || []).forEach(dt => {
      const opt = document.createElement('option');
      opt.value = dt.code;
      opt.textContent = dt.name;
      els.docTypeSelect.appendChild(opt);
    });

    if (docTypes.error)
        throw new Error(docTypes.error);

  } catch (err) {
        console.error('Dropdown load failed:', err);
        showResult( err);

  }
}

// Show result message
function showResult(message) {
  els.resultMsg.textContent = message;
  els.resultMsg.className = `dti-result dti-error dti-visible`;
}

// Handle form submission with robust error handling
async function handleFormSubmit(e) {
  e.preventDefault();

  const formData = new FormData(els.form);
  if (els.sourceSelect.value !== 'q10') formData.delete('quarter');

  try {
    const response = await fetch(`${BASE_URL}/create_run`, {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || errData.error || `HTTP ${response.status}`);
    }

    const data = await response.json();

    if (data.status === 'ok') {
      showResult(`✓ Run created: ${data.run_id}`, 'success');
    } else {
      showResult(data.detail || data.error || 'Unknown server error', 'error');
    }

  } catch (err) {
    console.error('Form submit failed:', err);
    showResult(`Submission error: ${err.message || 'Please try again'}`, 'error');
  }
}

// Initialize application
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