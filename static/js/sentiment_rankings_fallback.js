// sentiment_rankings_fallback.js — Sentiment Ranking Fallback screen
//
// The bot answers with free text, so the job here is to (a) never leave the
// user staring at a spinner when the bot is off, and (b) turn that text into
// something readable instead of one long paragraph.

const ENDPOINT = "/management_sentiment_rankings_fallback/analyze";

const $ = id => document.getElementById(id);

// The five metrics the reports expose. Any of them appearing in the answer is
// highlighted, so the user can see which number the bot actually ranked by.
const SCORE_KEYS = [
  "mdna_sentiment",
  "outlook_sentiment",
  "forward_ratio",
  "hedge_ratio",
  "financial_sentences"
];

// ── Score reference ───────────────────────────────────────────────────────────
$("btnHelp").addEventListener("click", () => {
  const help = $("scoreHelp");
  const open = help.hidden;
  help.hidden = !open;
  $("btnHelp").setAttribute("aria-expanded", String(open));
  $("btnHelp").textContent = open ? "Hide the score reference" : "What can I ask for?";
});

// ── Quarter only applies to Q10 ───────────────────────────────────────────────
const datasetSel = $("k10Selector");
const quarterField = $("quarterField");
const quarterSel = $("quarterSelector");

datasetSel.addEventListener("change", () => {
  const isQuarterly = datasetSel.value === "Q10";
  quarterField.hidden = !isQuarterly;
  // A stale quarter travelling with a K10 request builds a nonsense question,
  // so the value is cleared whenever the field goes away.
  if (!isQuarterly) quarterSel.value = "";
});

// ── Rendering helpers ─────────────────────────────────────────────────────────
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function highlightScores(html) {
  SCORE_KEYS.forEach(key => {
    const pattern = new RegExp(`\\b${key}\\b`, "g");
    html = html.replace(pattern, `<span class="srfb-score-chip">${key}</span>`);
  });
  return html;
}

function showResult(html, kind) {
  const box = $("result");
  box.hidden = false;
  box.className = "srfb-result" + (kind ? ` srfb-result-${kind}` : "");
  box.innerHTML = html;
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderAnswer(text) {
  // The bot marks the calendar block with its own heading; splitting there
  // keeps the filing dates out of the narrative and in their own panel.
  const [body, calendar] = String(text).split("SEC Filing Calendar:");

  const paragraphs = body
    .split(/\n{2,}/)
    .map(block => block.trim())
    .filter(Boolean)
    .map(block => `<p class="srfb-answer-p">${highlightScores(escapeHtml(block)).replace(/\n/g, "<br>")}</p>`)
    .join("");

  let html = `<div class="srfb-answer">
      <div class="srfb-result-head">
        <span class="srfb-result-title">Bot answer</span>
        <button type="button" class="srfb-btn-ghost srfb-btn-mini" onclick="copyAnswer()">Copy</button>
      </div>
      ${paragraphs || '<p class="srfb-answer-p">The bot answered with an empty message.</p>'}
    </div>`;

  if (calendar) {
    const lines = calendar
      .split("\n")
      .map(line => line.trim())
      .filter(Boolean)
      .map(line => `<li>${escapeHtml(line)}</li>`)
      .join("");

    html += `<div class="srfb-calendar">
        <div class="srfb-calendar-title">SEC filing calendar</div>
        <ul class="srfb-calendar-list">${lines}</ul>
      </div>`;
  }

  return html;
}

function copyAnswer() {
  const box = $("result");
  navigator.clipboard.writeText(box.innerText).catch(() => {});
}

function renderError(kind, message) {
  // Each failure gets its own wording: "the bot is off" and "the bot is slow"
  // need different reactions from the user.
  const titles = {
    unreachable: "The ranking bot is not answering",
    timeout: "The bot took too long",
    unexpected: "Something broke on the way to the bot",
    network: "The dashboard could not be reached"
  };

  const hints = {
    unreachable: "Check that the bot container is up, then run the query again. " +
                 "Nothing was lost — the question was never delivered.",
    timeout: "The question reached the bot but no answer came back in time. " +
             "A narrower query (one dataset, one year) usually comes back faster.",
    unexpected: "Worth a look at the dashboard log: this is not a bot being off.",
    network: "The browser could not talk to the dashboard itself. Reload the page and retry."
  };

  return `<div class="srfb-error">
      <div class="srfb-error-title">${escapeHtml(titles[kind] || titles.unexpected)}</div>
      <div class="srfb-error-msg">${escapeHtml(message || "")}</div>
      <div class="srfb-error-hint">${escapeHtml(hints[kind] || hints.unexpected)}</div>
    </div>`;
}

function showLoadingSkeleton() {
  showResult(`
    <div class="srfb-loading">
      <div class="srfb-loading-header">
        <div class="srfb-loading-spinner"></div>
        <span class="srfb-loading-label">Asking the bot&hellip;</span>
      </div>
      <div class="srfb-skeleton">
        <div class="srfb-skeleton-bar"></div>
        <div class="srfb-skeleton-bar"></div>
        <div class="srfb-skeleton-bar"></div>
        <div class="srfb-skeleton-bar"></div>
      </div>
    </div>`, "loading");
}

// ── Submit ────────────────────────────────────────────────────────────────────
$("fallbackForm").addEventListener("submit", async function (e) {
  e.preventDefault();

  const btn = $("btnSearch");
  const label = $("btnSearchLabel");

  btn.disabled = true;
  label.textContent = "Searching\u2026";
  showLoadingSkeleton();

  try {
    const resp = await fetch(ENDPOINT, { method: "POST", body: new FormData(this) });

    // A failed run still returns JSON with error_kind, so the body is read
    // before looking at the status code.
    let json;
    try {
      json = await resp.json();
    } catch (parseError) {
      showResult(renderError("unexpected",
        `The server answered with status ${resp.status} and no readable body.`), "error");
      return;
    }

    if (json.message === "ok") {
      showResult(renderAnswer(json.bot_response), "ok");
    } else {
      showResult(renderError(json.error_kind, json.error), "error");
    }

  } catch (networkError) {
    showResult(renderError("network", String(networkError)), "error");

  } finally {
    btn.disabled = false;
    label.textContent = "Search";
  }
});
