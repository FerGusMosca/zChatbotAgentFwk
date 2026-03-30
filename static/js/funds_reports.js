/**
 * Funds Reports (#10-Rag ZeroHedge) – Frontend logic
 */

const form       = document.getElementById('rankingForm');
const btn        = form.querySelector('button');
const errorMsg   = document.getElementById('errorMsg');
const resultDiv  = document.getElementById('result');

form.addEventListener('submit', async (e) => {
    e.preventDefault();

    errorMsg.textContent = '';
    resultDiv.textContent = 'Processing…';

    const query = form.query.value.trim();
    if (!query) {
        errorMsg.textContent = 'Please enter a query.';
        resultDiv.textContent = '';
        return;
    }

    btn.classList.add('loading');
    btn.disabled = true;

    const formData = new FormData(form);

    try {
        const res = await fetch('/funds_reports/analyze', {
            method: 'POST',
            body: formData
        });

        const data = await res.json();

        if (data.message === 'ok') {
            resultDiv.innerHTML = data.bot_response.replace(/\n/g, '<br>');
            showCopyBtn();
        } else {
            throw new Error(data.bot_response || 'Unknown error from bot');
        }

    } catch (err) {
        resultDiv.textContent = `Error: ${err.message}`;
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
});

function showCopyBtn() {
    const existing = document.getElementById('copyBtn');
    if (existing) existing.remove();

    const path     = form.processed_folder.value || 'Default';
    const question = form.query.value.trim();
    const answer   = resultDiv.innerText;

    const btn = document.createElement('button');
    btn.id = 'copyBtn';
    btn.className = 'fr-btn';
    btn.style.cssText = 'margin-top: 12px; width: 100%; background: linear-gradient(135deg, #1a3a1a, #2ea043);';
    btn.innerHTML = '<span class="fr-btn-text">📋 Copy to clipboard</span>';

    btn.addEventListener('click', async () => {
        const text = `PATH: ${path}\n\nQUESTION: ${question}\n\nANSWER:\n${answer}`;
        await navigator.clipboard.writeText(text);
        btn.querySelector('.fr-btn-text').textContent = '✅ Copied!';
        setTimeout(() => btn.querySelector('.fr-btn-text').textContent = '📋 Copy to clipboard', 2000);
    });

    resultDiv.insertAdjacentElement('afterend', btn);
}
