// static/js/sentiment.js - Management Sentiment page logic
const reportSel = document.getElementById('report');
const quarterSel = document.getElementById('quarter');
const form = document.getElementById('sentimentForm');
const btn = form.querySelector('button');
const errorMsg = document.getElementById('errorMsg');
const resultDiv = document.getElementById('result');

// Show/hide quarter field based on report type
function updateLayout() {
  const isQ10 = reportSel.value === 'Q10';
  quarterSel.style.display = isQ10 ? 'block' : 'none';
  quarterSel.style.gridArea = 'quarter';
}

reportSel.addEventListener('change', updateLayout);
window.addEventListener('resize', updateLayout);
updateLayout();

// Form submission with validation and loading state
form.addEventListener('submit', async e => {
  e.preventDefault();

  // Clear previous messages
  errorMsg.classList.remove('show');
  errorMsg.textContent = '';
  resultDiv.innerHTML = '';

  // Manual validation
  const symbol = form.symbol.value.trim();
  const year = form.year.value;
  const report = form.report.value;
  const quarter = report === 'Q10' ? form.quarter.value : 'ok';

  if (!symbol || !year || !report || (report === 'Q10' && !quarter)) {
    errorMsg.textContent = 'Please fill in all fields to search for sentiment.';
    errorMsg.classList.add('show');
    return;
  }

  // Show loading spinner
  btn.classList.add('loading');

  try {
    const res = await fetch(form.action, {
      method: 'POST',
      body: new FormData(form)
    });

    if (!res.ok) throw new Error('Server error');

    const data = await res.json();
    const parsed = JSON.parse(data.bot_response);

    // Render results
    resultDiv.innerHTML = `
      <table>
        <tr><th>Confidence</th><td>${parsed.Confidence || 'N/A'}</td></tr>
        <tr><th>Source</th><td>${parsed.Source || 'N/A'}</td></tr>
        <tr><th>Key Topics</th><td><ul>${(parsed.KeyTopics || []).map(t => `<li>${t}</li>`).join('') || 'N/A'}</ul></td></tr>
      </table>`;
  } catch (err) {
    resultDiv.innerHTML = `<p style="color:#f85149; font-weight:bold;">Error: ${err.message}</p>`;
  } finally {
    btn.classList.remove('loading');
  }
});