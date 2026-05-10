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
            showCopyBtn(data.bot_response);
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

function showCopyBtn(rawAnswer) {
    const existing = document.getElementById('copyContainer');
    if (existing) existing.remove();

    const folder   = form.processed_folder.value || 'Default';
    const question = form.query.value.trim();
    const answer   = rawAnswer;
    const json     = JSON.stringify({ folder, question, answer }, null, 2);

    const container = document.createElement('div');
    container.id = 'copyContainer';
    container.style.cssText = 'margin-top: 12px;';
    container.innerHTML =
        '<button type="button" id="copyBtn" class="fr-btn" ' +
            'style="width:100%;background:linear-gradient(135deg,#1a3a1a,#2ea043);">' +
            '<span class="fr-btn-text">📋 Copy JSON</span>' +
        '</button>' +
        '<details id="copyDetails" style="margin-top:10px;">' +
            '<summary style="cursor:pointer;user-select:none;color:#8B949E;' +
                "font-family:'IBM Plex Mono',monospace;font-size:11px;padding:4px 0;\">" +
                '👁 Show / hide JSON' +
            '</summary>' +
            '<textarea id="copyJsonArea" readonly rows="12" ' +
                'style="width:100%;margin-top:8px;padding:12px;background:#010409;' +
                'border:1px solid #21262D;border-radius:8px;color:#C9D1D9;' +
                "font-family:'IBM Plex Mono',monospace;font-size:12px;" +
                'line-height:1.5;resize:vertical;box-sizing:border-box;"></textarea>' +
        '</details>';

    resultDiv.insertAdjacentElement('afterend', container);

    const ta      = document.getElementById('copyJsonArea');
    const details = document.getElementById('copyDetails');
    ta.value = json;

    document.getElementById('copyBtn').addEventListener('click', async () => {
        const lbl = document.querySelector('#copyBtn .fr-btn-text');
        try {
            await navigator.clipboard.writeText(json);
            lbl.textContent = '✅ Copied!';
            // Stays hidden — clipboard worked, no need to show the textarea
        } catch (err) {
            // Fallback: open the panel, select the text, ask for Ctrl+C
            details.open = true;
            ta.focus();
            ta.select();
            lbl.textContent = '👆 Press Ctrl+C';
        }
        setTimeout(() => { lbl.textContent = '📋 Copy JSON'; }, 2500);
    });
}
