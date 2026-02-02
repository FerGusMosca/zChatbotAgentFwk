// deep_company_analysis.js - Simple form-based logic

const BASE_URL = '/deep_company_analysis';

// DOM elements
const els = {
  form: document.getElementById('analysisForm'),
  symbolInput: document.getElementById('symbolInput'),
  docTypeSelect: document.getElementById('docTypeSelect'),
  yearInput: document.getElementById('yearInput'),
  quarterSelect: document.getElementById('quarterSelect'),
  freeTextRow: document.getElementById('freeTextRow'),
  freeTextArea: document.getElementById('freeTextArea'),
  sentimentBtn: document.getElementById('sentimentBtn'),
  topicsBtn: document.getElementById('topicsBtn'),
  freeAnalysisBtn: document.getElementById('freeAnalysisBtn'),
  freeAnalysisPromptSection: document.getElementById('freeAnalysisPromptSection'),
  freeAnalysisPrompt: document.getElementById('freeAnalysisPrompt'),
  resultMessage: document.getElementById('resultMessage'),
  topicModal: document.getElementById('topicModal'),
  closeTopicModal: document.getElementById('closeTopicModal'),
  tagNameInput: document.getElementById('tagNameInput'),
  topicsInput: document.getElementById('topicsInput'),
  submitTopics: document.getElementById('submitTopics'),
  topicProgressContainer: document.getElementById('topicProgressContainer'),
  topicProgressMessages: document.getElementById('topicProgressMessages')
};

// State
let currentSymbol = null;
let symbolValidated = false;

// Initialize
function init() {
  setupEventListeners();
}

// Setup event listeners
function setupEventListeners() {
  // Document type change
  els.docTypeSelect.addEventListener('change', handleDocTypeChange);

  // Symbol validation on blur
  els.symbolInput.addEventListener('blur', validateSymbol);

  // Action buttons
  els.sentimentBtn.addEventListener('click', () => handleAnalysis('sentiment'));
  els.topicsBtn.addEventListener('click', openTopicModal);
  els.freeAnalysisBtn.addEventListener('click', () => handleAnalysis('free'));

  // Topic modal
  els.closeTopicModal.addEventListener('click', closeTopicModal);
  els.topicModal.addEventListener('click', (e) => {
    if (e.target === els.topicModal) closeTopicModal();
  });
  els.submitTopics.addEventListener('click', handleTopicAnalysis);
}

// Handle document type change
function handleDocTypeChange() {
  const docType = els.docTypeSelect.value;

  // Show/hide quarter select for 10Q
  if (docType === '10Q') {
    els.quarterSelect.classList.remove('dca-hidden');
    els.quarterSelect.required = true;
  } else {
    els.quarterSelect.classList.add('dca-hidden');
    els.quarterSelect.required = false;
    els.quarterSelect.value = '';
  }

  // Show/hide free text area for FREE_TEXT
  if (docType === 'FREE_TEXT') {
    els.freeTextRow.classList.remove('dca-hidden');
    els.freeTextArea.required = true;
    els.freeAnalysisBtn.classList.remove('dca-hidden');
    els.freeAnalysisPromptSection.classList.remove('dca-hidden');
  } else {
    els.freeTextRow.classList.add('dca-hidden');
    els.freeTextArea.required = false;
    els.freeTextArea.value = '';
    els.freeAnalysisBtn.classList.add('dca-hidden');
    els.freeAnalysisPromptSection.classList.add('dca-hidden');
  }
}

// Validate symbol against backend
async function validateSymbol() {
  const symbol = els.symbolInput.value.trim().toUpperCase();

  if (!symbol) {
    symbolValidated = false;
    return;
  }

  try {
    const formData = new FormData();
    formData.append('symbol', symbol);

    const response = await fetch(`${BASE_URL}/validate_symbol`, {
      method: 'POST',
      body: formData
    });

    const data = await response.json();

    if (data.status === 'ok' && data.valid) {
      currentSymbol = data.symbol;
      symbolValidated = true;
      showResult(`✓ Symbol ${data.symbol} validated`, 'success');
    } else {
      symbolValidated = false;
      showResult(`✗ Symbol ${symbol} not found in database`, 'error');
      els.symbolInput.focus();
    }

  } catch (err) {
    console.error('Symbol validation failed:', err);
    showResult(`Error validating symbol: ${err.message}`, 'error');
    symbolValidated = false;
  }
}

// Open topic modal
function openTopicModal() {
  // Validate form first
  if (!els.form.checkValidity()) {
    els.form.reportValidity();
    return;
  }

  if (!symbolValidated) {
    showResult('Please enter a valid symbol first', 'error');
    els.symbolInput.focus();
    return;
  }

  // Reset modal state
  els.tagNameInput.value = '';
  els.topicsInput.value = '';
  els.topicProgressContainer.classList.add('dca-hidden');
  els.topicProgressMessages.innerHTML = '';

  els.topicModal.classList.remove('dca-hidden');
}

// Close topic modal
function closeTopicModal() {
  els.topicModal.classList.add('dca-hidden');
}

// Handle topic analysis from modal
async function handleTopicAnalysis() {
  const tagName = els.tagNameInput.value.trim();
  const topicsText = els.topicsInput.value.trim();

  if (!tagName) {
    alert('Please enter a tag name (e.g., ai_innovation)');
    els.tagNameInput.focus();
    return;
  }

  if (!topicsText) {
    alert('Please enter at least one topic phrase');
    els.topicsInput.focus();
    return;
  }

  const btn = els.submitTopics;
  btn.classList.add('loading');

  // Show progress container
  els.topicProgressContainer.classList.remove('dca-hidden');
  els.topicProgressMessages.innerHTML = '<div style="color:#58A6FF;">🚀 Starting analysis...</div>';

  try {
    const symbol = els.symbolInput.value.trim().toUpperCase();
    const docType = els.docTypeSelect.value;
    const year = els.yearInput.value;
    const quarter = els.quarterSelect.value || null;
    const freeText = els.freeTextArea.value || null;

    // Parse topics (one per line)
    const topicList = topicsText.split('\n')
      .map(t => t.trim())
      .filter(t => t);

    // Build tag JSON: { "tag_name": ["phrase1", "phrase2", ...] }
    const tagJson = JSON.stringify({
      [tagName]: topicList
    });

    const formData = new FormData();
    formData.append('symbol', symbol);
    formData.append('doc_type', docType);
    formData.append('year', year);
    formData.append('tag_name', tagName);
    formData.append('tag_json', tagJson);
    if (quarter) formData.append('quarter', quarter);
    if (freeText) formData.append('free_text', freeText);

    const response = await fetch(`${BASE_URL}/analyze_topics`, {
      method: 'POST',
      body: formData
    });

    const data = await response.json();

    // Display progress messages if available
    if (data.progress_messages && data.progress_messages.length > 0) {
      displayProgressMessages(data.progress_messages);
    }

    // Don't check data.status === 'ok' because MCP returns 'completed'
    if (!response.ok) {
      throw new Error(data.message || `HTTP ${response.status}`);
    }

    // Wait a bit to show final progress
    await new Promise(resolve => setTimeout(resolve, 500));

    // Close modal
    closeTopicModal();

    // Display results
    displayResults(data, 'topics');

  } catch (err) {
    console.error('Topic analysis failed:', err);

    // Show error in progress
    els.topicProgressMessages.innerHTML += `<div style="color:#F85149;">❌ Error: ${err.message}</div>`;

    alert(`Analysis error: ${err.message}`);
  } finally {
    btn.classList.remove('loading');
  }
}

// Display progress messages in modal
function displayProgressMessages(messages) {
  let html = '<div style="color:#58A6FF;">🚀 Starting analysis...</div>';

  messages.forEach(msg => {
    // Color code different message types
    let color = '#8B949E';
    let icon = '📝';

    if (msg.includes('ERROR') || msg.includes('❌')) {
      color = '#F85149';
      icon = '❌';
    } else if (msg.includes('✅') || msg.includes('completed')) {
      color = '#3FB950';
      icon = '✅';
    } else if (msg.includes('🚀') || msg.includes('Starting')) {
      color = '#58A6FF';
      icon = '🚀';
    } else if (msg.includes('🔍') || msg.includes('Loading')) {
      color = '#9E6A03';
      icon = '🔍';
    }

    html += `<div style="color:${color}; margin-top:4px;">${icon} ${escapeHtml(msg)}</div>`;
  });

  els.topicProgressMessages.innerHTML = html;

  // Auto-scroll to bottom
  els.topicProgressContainer.scrollTop = els.topicProgressContainer.scrollHeight;
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Handle analysis button clicks (sentiment and free only now)
async function handleAnalysis(analysisType) {
  // Validate form
  if (!els.form.checkValidity()) {
    els.form.reportValidity();
    return;
  }

  if (!symbolValidated) {
    showResult('Please enter a valid symbol first', 'error');
    els.symbolInput.focus();
    return;
  }

  // Get form data
  const symbol = els.symbolInput.value.trim().toUpperCase();
  const docType = els.docTypeSelect.value;
  const year = els.yearInput.value;
  const quarter = els.quarterSelect.value || null;
  const freeText = els.freeTextArea.value || null;

  // Special validation for free analysis
  if (analysisType === 'free') {
    if (docType !== 'FREE_TEXT') {
      showResult('Free Analysis is only available for Free Text documents', 'error');
      return;
    }

    const prompt = els.freeAnalysisPrompt.value.trim();
    if (!prompt) {
      showResult('Please enter a custom prompt for Free Analysis', 'error');
      els.freeAnalysisPrompt.focus();
      return;
    }
  }

  // Get the appropriate button
  let btn;
  if (analysisType === 'sentiment') btn = els.sentimentBtn;
  else if (analysisType === 'topics') btn = els.topicsBtn;
  else if (analysisType === 'free') btn = els.freeAnalysisBtn;

  btn.classList.add('loading');
  els.resultMessage.classList.remove('dca-visible');

  try {
    let endpoint;
    const formData = new FormData();
    formData.append('symbol', symbol);
    formData.append('doc_type', docType);
    formData.append('year', year);
    if (quarter) formData.append('quarter', quarter);
    if (freeText) formData.append('free_text', freeText);

    if (analysisType === 'sentiment') {
      endpoint = `${BASE_URL}/analyze_sentiment`;
    } else if (analysisType === 'topics') {
      endpoint = `${BASE_URL}/analyze_topics`;
    } else if (analysisType === 'free') {
      endpoint = `${BASE_URL}/free_analysis`;
      formData.append('prompt', els.freeAnalysisPrompt.value.trim());
    }

    const response = await fetch(endpoint, {
      method: 'POST',
      body: formData
    });

    const data = await response.json();

    // For sentiment/topic analysis, don't check data.status === 'ok' because MCP returns 'completed'
    // Only check HTTP response status
    if (!response.ok) {
      throw new Error(data.message || `HTTP ${response.status}`);
    }

    displayResults(data, analysisType);

  } catch (err) {
    console.error('Analysis failed:', err);
    showResult(`Analysis error: ${err.message}`, 'error');
  } finally {
    btn.classList.remove('loading');
  }
}

// Display analysis results
function displayResults(data, analysisType) {
  let html = '';

  if (analysisType === 'sentiment') {
    // Check if analysis failed (MCP returns status: "failed" or "error")
    if (data.status === 'failed' || data.status === 'error') {
      html = `
        <div class="dca-result-display">
          <h4>❌ Analysis Failed</h4>
          <p style="color:#F85149; font-size:15px;">
            <strong>Error:</strong> ${data.message || 'Unknown error occurred'}
          </p>
          ${data.error_type ? `<p style="color:#8B949E; font-size:13px;">Error type: ${data.error_type}</p>` : ''}
        </div>
      `;
    }
    // Check if analysis succeeded (MCP returns status: "completed")
    else if (data.status === 'completed' && data.analysis) {
      const analysis = data.analysis || {};
      const metrics = analysis.metrics || {};
      const topPos = analysis.top_positive || [];
      const topNeg = analysis.top_negative || [];
      const forwardSnippets = analysis.forward_snippets || [];

      html = `
        <div class="dca-result-display">
          <h4>📊 Sentiment Analysis Results</h4>

          <div style="background:#161B22; padding:16px; border-radius:8px; margin-bottom:16px;">
            <div style="color:#8B949E; font-size:13px; margin-bottom:8px;">
              <strong>Symbol:</strong> ${data.symbol || 'N/A'} |
              <strong>Year:</strong> ${data.year || 'N/A'} |
              <strong>Period:</strong> ${data.period || 'N/A'}
            </div>
          </div>

          <div class="metric">
            <span class="metric-label">MD&A Sentiment Score</span>
            <span class="metric-value" style="color: ${getToneColor(metrics.mdna_sentiment || 0)};">
              ${(metrics.mdna_sentiment || 0).toFixed(3)}
            </span>
          </div>

          <div class="metric">
            <span class="metric-label">Financial Sentences Analyzed</span>
            <span class="metric-value">${metrics.financial_sentences || 0}</span>
          </div>

          <div class="metric">
            <span class="metric-label">Forward-Looking Language</span>
            <span class="metric-value" style="color: ${(metrics.forward_ratio || 0) > 0.3 ? '#3FB950' : '#8B949E'};">
              ${((metrics.forward_ratio || 0) * 100).toFixed(1)}%
            </span>
          </div>

          <div class="metric">
            <span class="metric-label">Hedging Language</span>
            <span class="metric-value" style="color: ${(metrics.hedge_ratio || 0) > 0.2 ? '#F85149' : '#8B949E'};">
              ${((metrics.hedge_ratio || 0) * 100).toFixed(1)}%
            </span>
          </div>

          ${topPos.length > 0 ? `
            <h5 style="color:#3FB950; margin-top:24px; font-size:16px;">✅ Most Positive Statements:</h5>
            <div style="max-height:200px; overflow-y:auto;">
              ${topPos.map(item => `
                <div style="background:#1A3421; padding:12px; margin:8px 0; border-radius:6px; border-left:3px solid #3FB950;">
                  <div style="color:#E6EDF3; font-size:14px; line-height:1.5; margin-bottom:6px;">${item.sent}</div>
                  <div style="color:#8B949E; font-size:12px;">Score: ${item.score.toFixed(3)}</div>
                </div>
              `).join('')}
            </div>
          ` : ''}

          ${topNeg.length > 0 ? `
            <h5 style="color:#F85149; margin-top:24px; font-size:16px;">⚠️ Most Negative Statements:</h5>
            <div style="max-height:200px; overflow-y:auto;">
              ${topNeg.map(item => `
                <div style="background:#3A1214; padding:12px; margin:8px 0; border-radius:6px; border-left:3px solid #F85149;">
                  <div style="color:#E6EDF3; font-size:14px; line-height:1.5; margin-bottom:6px;">${item.sent}</div>
                  <div style="color:#8B949E; font-size:12px;">Score: ${item.score.toFixed(3)}</div>
                </div>
              `).join('')}
            </div>
          ` : ''}
        </div>
      `;
    } else {
      // Unexpected response format
      html = `
        <div class="dca-result-display">
          <h4>⚠️ Unexpected Response</h4>
          <p style="color:#9E6A03;">Received data but in unexpected format. Status: ${data.status || 'unknown'}</p>
          <pre style="background:#161B22; padding:12px; border-radius:6px; font-size:12px; overflow-x:auto;">${JSON.stringify(data, null, 2)}</pre>
        </div>
      `;
    }

  } else if (analysisType === 'topics') {
    // Check if analysis failed
    if (data.status === 'failed' || data.status === 'error') {
      html = `
        <div class="dca-result-display">
          <h4>❌ Topic Analysis Failed</h4>
          <p style="color:#F85149; font-size:15px;">
            <strong>Error:</strong> ${data.message || 'Unknown error occurred'}
          </p>
          ${data.error_type ? `<p style="color:#8B949E; font-size:13px;">Error type: ${data.error_type}</p>` : ''}
        </div>
      `;
    }
    // Check if analysis succeeded
    else if (data.status === 'completed' && data.analysis) {
      const analysis = data.analysis || {};
      const topics = analysis.topics || {};
      const topicKeys = Object.keys(topics);

      html = `
        <div class="dca-result-display">
          <h4>🏷️ Topic Analysis Results</h4>

          <div style="background:#161B22; padding:16px; border-radius:8px; margin-bottom:16px;">
            <div style="color:#8B949E; font-size:13px; margin-bottom:8px;">
              <strong>Symbol:</strong> ${data.symbol || 'N/A'} |
              <strong>Year:</strong> ${data.year || 'N/A'} |
              <strong>Period:</strong> ${data.period || 'N/A'}
            </div>
            <div style="color:#8B949E; font-size:13px;">
              <strong>Source:</strong> ${data.source || 'N/A'} |
              <strong>Topics:</strong> ${topicKeys.length}
            </div>
          </div>

          ${topicKeys.map(topicKey => {
            const topic = topics[topicKey];
            const matches = topic.matches || [];
            const topScore = topic.top_score || 0;

            return `
              <div class="dca-topic-card" style="margin-bottom:20px; background:#161B22; padding:16px; border-radius:8px; border-left:4px solid #58A6FF;">
                <h5 style="color:#58A6FF; margin:0 0 12px 0; font-size:18px;">
                  ${topicKey.replace(/_/g, ' ').toUpperCase()}
                </h5>

                <div style="margin-bottom:16px;">
                  <span style="color:#8B949E; font-size:14px;">
                    Top Score: <span style="color:#3FB950; font-weight:bold;">${(topScore * 100).toFixed(1)}%</span> |
                    Matches: <span style="color:#58A6FF; font-weight:bold;">${matches.length}</span>
                  </span>
                </div>

                ${topic.summary ? `
                  <div style="color:#8B949E; font-size:13px; font-style:italic; margin-bottom:16px; padding:12px; background:#0D1117; border-radius:6px;">
                    ${topic.summary}
                  </div>
                ` : ''}

                ${matches.length > 0 ? `
                  <div style="margin-top:16px;">
                    <h6 style="color:#C9D1D9; font-size:14px; margin-bottom:12px;">📝 Top Matches:</h6>
                    <div style="max-height:400px; overflow-y:auto;">
                      ${matches.map((match, idx) => `
                        <div style="background:#0D1117; padding:12px; margin-bottom:12px; border-radius:6px; border-left:3px solid ${getScoreColor(match.score)};">
                          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                            <span style="color:#58A6FF; font-size:12px; font-weight:bold;">
                              Match #${idx + 1} | Chunk ${match.chunk_idx || 'N/A'}
                            </span>
                            <span style="color:${getScoreColor(match.score)}; font-size:12px; font-weight:bold;">
                              ${(match.score * 100).toFixed(1)}%
                            </span>
                          </div>

                          ${match.matched_phrase ? `
                            <div style="color:#3FB950; font-size:13px; margin-bottom:8px; padding:8px; background:#1A3421; border-radius:4px;">
                              <strong>Phrase:</strong> "${match.matched_phrase}"
                            </div>
                          ` : ''}

                          <div style="color:#C9D1D9; font-size:13px; line-height:1.6;">
                            ${match.chunk_text || 'No text available'}
                          </div>
                        </div>
                      `).join('')}
                    </div>
                  </div>
                ` : ''}
              </div>
            `;
          }).join('')}
        </div>
      `;
    } else {
      // Unexpected response format
      html = `
        <div class="dca-result-display">
          <h4>⚠️ Unexpected Response</h4>
          <p style="color:#9E6A03;">Received data but in unexpected format. Status: ${data.status || 'unknown'}</p>
          <pre style="background:#161B22; padding:12px; border-radius:6px; font-size:12px; overflow-x:auto;">${JSON.stringify(data, null, 2)}</pre>
        </div>
      `;
    }

  } else if (analysisType === 'free') {
    const analysis = data.analysis;
    html = `
      <div class="dca-result-display">
        <h4>🤖 Free Analysis Results</h4>
        <p style="color:#8B949E; font-size:14px; margin-bottom:16px;"><strong>Prompt:</strong> ${data.prompt}</p>

        <div style="background:#161B22; padding:16px; border-radius:8px; border:1px solid #30363D; margin-bottom:16px;">
          <pre style="white-space:pre-wrap; margin:0; color:#C9D1D9; font-size:14px; line-height:1.6;">${analysis.response}</pre>
        </div>

        <h5 style="color:#58A6FF; margin-top:20px;">Extracted Concepts:</h5>
        <ul>
          ${analysis.extracted_concepts.map(concept => `<li>${concept}</li>`).join('')}
        </ul>
      </div>
    `;
  }

  els.resultMessage.innerHTML = html;
  els.resultMessage.classList.add('dca-visible');
  els.resultMessage.classList.remove('dca-error');
  els.resultMessage.classList.add('dca-success');
}

// Show result message
function showResult(message, type) {
  els.resultMessage.innerHTML = message;
  els.resultMessage.className = `dca-result dca-visible dca-${type}`;
}

// Get color based on tone score
function getToneColor(score) {
  if (score > 0.7) return '#3FB950';
  if (score > 0.4) return '#9E6A03';
  return '#F85149';
}

// Get color based on match score (for topics)
function getScoreColor(score) {
  if (score > 0.6) return '#3FB950';  // Green
  if (score > 0.4) return '#9E6A03';  // Yellow
  return '#F85149';  // Red
}

// Start app
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}