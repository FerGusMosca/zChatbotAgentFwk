// Handles the Competition form submission and render
const reportSel = document.getElementById('report');
const quarterSel = document.getElementById('quarter');
const form = document.getElementById('competitionForm');
const btn = form.querySelector('button');
const errorMsg = document.getElementById('errorMsg');
const resultDiv = document.getElementById('result');

function updateLayout() {
  const isQ10 = reportSel.value === 'Q10';
  quarterSel.style.display = isQ10 ? 'block' : 'none';
}
reportSel.addEventListener('change', updateLayout);
window.addEventListener('resize', updateLayout);
updateLayout();

form.addEventListener('submit', async e => {
  e.preventDefault();
  errorMsg.classList.remove('show');
  errorMsg.textContent = '';
  resultDiv.innerHTML = '<div style="padding:14px;color:#9aa4b2">⏳ Loading...</div>';

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

  btn.classList.add('loading');
  const formData = new FormData(form);
  if (report !== 'Q10') formData.delete('quarter');

  try {
    const res = await fetch("/management_competition/analyze", { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.bot_response) throw new Error('Missing bot_response');

    let parsed = typeof data.bot_response === 'string' ? JSON.parse(data.bot_response) : data.bot_response;

    const conf = parsed.Confidence || 'N/A';
    const market = parsed.MarketCompetition?.map(t => `<li>${t}</li>`).join('') || '<li>N/A</li>';
    const reg = parsed.RegulatoryPressures?.map(t => `<li>${t}</li>`).join('') || '<li>N/A</li>';
    const ops = parsed.OperationalThreats?.map(t => `<li>${t}</li>`).join('') || '<li>N/A</li>';
    const strat = parsed.StrategicRisks?.map(t => `<li>${t}</li>`).join('') || '<li>N/A</li>';
    const src = parsed.Source || 'N/A';

    resultDiv.innerHTML = `
      <div class="confidence"><strong>Confianza:</strong> ${conf}</div>
      <div class="section"><h3>🏁 Competencia de Mercado</h3><ul>${market}</ul></div>
      <div class="section"><h3>⚖️ Presiones Regulatorias</h3><ul>${reg}</ul></div>
      <div class="section"><h3>⚙️ Amenazas Operativas</h3><ul>${ops}</ul></div>
      <div class="section"><h3>🎯 Riesgos Estratégicos</h3><ul>${strat}</ul></div>
      <div class="source"><strong>Fuente:</strong> ${src}</div>`;
  } catch (err) {
    resultDiv.innerHTML = `<p style="color:#f85149;font-weight:bold;padding:20px;">🔥 ERROR: ${err.message}</p>`;
  } finally {
    btn.classList.remove('loading');
  }
});
