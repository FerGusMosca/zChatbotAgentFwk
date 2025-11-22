// ===== UI: search ticker =====
async function searchTicker() {
    const q = document.getElementById("searchInput").value.trim();
    const box = document.getElementById("searchResults");

    if (q.length < 2) {
        box.innerHTML = "";
        return;
    }

    const res = await fetch(`/process_news/search?query=${encodeURIComponent(q)}`);
    const items = await res.json();

    box.innerHTML = items.map(x =>
        `<div class="result-item" onclick="selectSecurity('${x.ticker}')">
            ${x.ticker} — ${x.name}
        </div>`
    ).join("");
}

function selectSecurity(ticker) {
    document.getElementById("searchInput").value = ticker;
    document.getElementById("selectedSecurity").value = ticker;
    document.getElementById("searchResults").innerHTML = "";
}

// ===== RUN PROCESS WITH STREAMING =====
async function runProcessNews(ev) {
    ev.preventDefault();

    const symbol = document.getElementById("selectedSecurity").value.trim();
    if (!symbol) {
        alert("Select a security first.");
        return;
    }

    const outputBox = document.getElementById("outputBox");
    outputBox.textContent = "";

    const runBtn = document.getElementById("runBtn");
    runBtn.classList.add("loading");   // show spinner

    await new Promise(r => requestAnimationFrame(() => r()));

    const formData = new FormData();
    formData.append("symbol", symbol);

    const resp = await fetch("/process_news/run_stream", {
        method: "POST",
        body: formData
    });

    if (!resp.body) {
        outputBox.textContent = "❌ No stream received";
        runBtn.classList.remove("loading");
        return;
    }

    // disable download button at start
    const dl = document.getElementById("downloadBtn");  // correct ID
    const dp = document.getElementById("downloadPromptBtn");
    dl.classList.remove("enabled-btn");
    dl.classList.add("disabled-btn");
    dp.classList.remove("enabled-btn");
    dp.classList.add("disabled-btn");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: false });
        outputBox.textContent += chunk;
        outputBox.scrollTop = outputBox.scrollHeight;

        // ===== ENABLE DOWNLOAD ONLY WHEN "event": "saved" APPEARS =====
        if (chunk.includes('"event": "saved"')) {
            dl.classList.remove("disabled-btn");
            dl.classList.add("enabled-btn");
            dp.classList.remove("disabled-btn");
            dp.classList.add("enabled-btn");
        }
    }

    runBtn.classList.remove("loading"); // hide spinner
}
