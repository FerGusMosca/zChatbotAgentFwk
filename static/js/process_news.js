async function searchTicker() {
    const q = document.getElementById("searchInput").value.trim();
    const box = document.getElementById("searchResults");
    box.innerHTML = "";

    if (q.length < 2) {
    box.innerHTML = "";
    return;
}

    const res = await fetch(`/process_news/search?query=${encodeURIComponent(q)}`);
    const data = await res.json();

    if (!Array.isArray(data) || data.length === 0) {
        box.innerHTML = "<div>No results</div>";
        return;
    }

    box.innerHTML = data.map(s => `
        <div onclick="selectSecurity(${s.security_id}, '${s.ticker}')">
            <b>${s.ticker}</b> — ${s.name}
        </div>
    `).join("");
}

function selectSecurity(id, ticker) {
    document.getElementById("selectedSecurity").value = id;
    document.getElementById("searchInput").value = ticker;
    document.getElementById("searchResults").innerHTML = "";
}

async function runProcessNews(evt) {
    evt.preventDefault();

    const secId = document.getElementById("selectedSecurity").value;
    const date = document.getElementById("dateInput").value;
    const out = document.getElementById("outputBox");
    const btn = document.getElementById("runBtn");

    if (!secId) {
        alert("Select a security.");
        return;
    }

    btn.disabled = true;
    btn.innerHTML = "⏳ Processing...";

    const res = await fetch("/process_news/run", {
        method: "POST",
        body: new URLSearchParams({
            security_id: secId,
            date: date
        })
    });

    const text = await res.text();
    out.innerHTML = text;

    btn.disabled = false;
    btn.innerHTML = "Run News Processor";
}
