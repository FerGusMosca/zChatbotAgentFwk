// static/js/sentiment.js — Management Sentiment logic (FULL FILE)

/*
  Handles the Management Sentiment search form, validation,
  and rendering of the bot’s JSON response.
*/

const reportSel = document.getElementById('report');
const quarterSel = document.getElementById('quarter');
const form = document.getElementById('sentimentForm');
const btn = form.querySelector('button');
const errorMsg = document.getElementById('errorMsg');
const resultDiv = document.getElementById('result');

/* Show or hide the "Quarter" field based on report type */
function updateLayout() {
  const isQ10 = reportSel.value === 'Q10';
  quarterSel.style.display = isQ10 ? 'block' : 'none';
  quarterSel.style.gridArea = 'quarter';
}
reportSel.addEventListener('change', updateLayout);
window.addEventListener('resize', updateLayout);
updateLayout();

/* Form submit handler */
form.addEventListener('submit', async e => {
  e.preventDefault();

  // Clear old messages
  errorMsg.classList.remove('show');
  errorMsg.textContent = '';

  // Show temporary placeholder
  resultDiv.innerHTML =
    '<div class="loading-placeholder" style="padding:14px;color:#9aa4b2">Loading...</div>';

  // Basic validation
  const symbol = form.symbol.value.trim().toUpperCase();
  const year = form.year.value;
  const report = form.report.value;
  const quarter = report === 'Q10' ? form.quarter.value : null;

  if (!symbol || !year || !report || (report === 'Q10' && !quarter)) {
    errorMsg.textContent = 'Please fill in all fields before searching.';
    errorMsg.classList.add('show');
    resultDiv.innerHTML = '';
    return;
  }

  // Add loading state
  btn.classList.add('loading');

  // Prepare FormData (remove quarter for K10)
  const formData = new FormData(form);
  if (report !== 'Q10') formData.delete('quarter');

  try {
    const res = await fetch("/management_sentiment/analyze", {
      method: 'POST',
      body: formData,
      cache: 'no-store',
      headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache'
      }
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`HTTP ${res.status}: ${text}`);
    }

    const data = await res.json();
    if (!data.bot_response) throw new Error('Missing bot_response field');

    // Robust parsing (handles string or object)
    let parsed;
    try {
      parsed = (typeof data.bot_response === 'string')
        ? JSON.parse(data.bot_response)
        : data.bot_response;
    } catch (e) {
      throw new Error('Invalid JSON in bot_response: ' + e.message);
    }

    // Render result
    const confidence = parsed.Confidence || 'N/A';
    const source = parsed.Source || 'N/A';
    const topics = Array.isArray(parsed.KeyTopics)
      ? parsed.KeyTopics.map(t => `<li>${t}</li>`).join('')
      : '<li>No topics found</li>';

    resultDiv.innerHTML = `
      <div class="confidence ${confidence.toLowerCase()}">
        Confidence: <strong>${confidence}</strong>
      </div>
      <div class="source">
        Source: ${source}
      </div>
      <div class="key-topics">
        <h3>Key Topics</h3>
        <ul>${topics}</ul>
      </div>
    `;
  } catch (err) {
    resultDiv.innerHTML = `
      <p style="color:#f85149;font-weight:bold;padding:20px;background:#1c1f26;border-radius:8px;">
        🔥 ERROR: ${err.message}
      </p>`;
    console.error('Sentiment error:', err);
  } finally {
    btn.classList.remove('loading');
  }
});
