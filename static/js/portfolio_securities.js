/* ---------- PAGINATION ---------- */
function goPage(page) {
    if (page < 1) return;
    document.getElementById("pageInput").value = page;
    document.getElementById("pfForm").submit();
}

/* ---------- MODAL ---------- */
function openAddModal() {
    document.getElementById("addModal").style.display = "flex";
}
function closeAddModal() {
    document.getElementById("addModal").style.display = "none";
}

/* ---------- TABS ---------- */
function showTab(id, evt) {
    document.querySelectorAll(".tab-content").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".tab-btn").forEach(x => x.classList.remove("active"));

    document.getElementById(id).classList.add("active");
    evt.target.classList.add("active");
}

/* ---------- SEARCH SECURITY ---------- */
async function searchSecurities() {
    const q = document.getElementById("searchInput").value.trim();
    const box = document.getElementById("searchResults");
    box.innerHTML = "";

    if (q.length < 2) return;

    const res = await fetch(`/portfolio_securities/search?query=${encodeURIComponent(q)}`);
    const data = await res.json();

    if (!Array.isArray(data) || data.length === 0) {
        box.innerHTML = "<div class='sr-item empty'>No results</div>";
        return;
    }

    box.innerHTML = data.map(s => `
      <div class="sr-item" onclick="addSingle(${s.security_id})">
          <b>${s.ticker}</b> — ${s.name}
      </div>
    `).join("");
}

/* ---------- ADD SINGLE ---------- */
async function addSingle(secId) {
    const portfolioId = document.getElementById("portfolioSelect").value;

    const form = new FormData();
    form.append("portfolio_id", portfolioId);
    form.append("security_id", secId);

    const res = await fetch("/portfolio_securities/add_single", {
        method: "POST",
        body: form
    });

    const data = await res.json();
    if (data.status === "ok") location.reload();
    else alert("ERROR: " + data.message);
}

/* ---------- IMPORT CSV ---------- */
async function importCSV(btn) {

    btn.disabled = true;
    const original = btn.innerHTML;
    btn.innerHTML = "⏳ Importing...";

    const csv = document.getElementById("csvInput").value.trim();
    const resultBox = document.getElementById("csvResult");
    const portfolioId = document.getElementById("portfolioSelect").value;

    if (!csv) {
        resultBox.innerHTML = "<span class='err'>CSV is empty</span>";
        btn.disabled = false;
        btn.innerHTML = original;
        return;
    }

    const form = new FormData();
    form.append("portfolio_id", portfolioId);
    form.append("csv_text", csv);

    const res = await fetch("/portfolio_securities/import_csv", {
        method: "POST",
        body: form
    });

    const data = await res.json();

    if (data.status !== "ok") {
        resultBox.innerHTML = `<span class='err'>ERROR: ${data.message}</span>`;
        btn.disabled = false;
        btn.innerHTML = original;
        return;
    }

    const rep = data.report;
    resultBox.innerHTML = `
        <div class="csv-summary">
            <div>Inserted: <strong>${rep.inserted}</strong></div>
            <div>Updated: <strong>${rep.updated}</strong></div>
            <div>Not Found:</div>
            <ul>${rep.not_found.map(x => `<li>${x}</li>`).join("")}</ul>
        </div>
    `;

    setTimeout(() => location.reload(), 1500);
}


function showLoader(btn){
    btn.innerHTML = "⏳ Loading...";
}

