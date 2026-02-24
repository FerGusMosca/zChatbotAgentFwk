function toggleChat() {
  const popup = document.getElementById("chat-popup");

  if (popup.style.display === "flex") {
    popup.style.display = "none";
  } else {
    popup.style.display = "flex";
    requestAnimationFrame(() => {
      popup.scrollTop = popup.scrollHeight;
      document.getElementById("user-input").focus();
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chat-form");
  const inputField = document.getElementById("user-input");
  const historyDiv = document.getElementById("chat-history");
  const sendBtn = document.getElementById("send-btn");

  inputField.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.dispatchEvent(new Event("submit"));
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = inputField.value.trim();
    if (!question) return;

    sendBtn.disabled = true;
    inputField.disabled = true;
    sendBtn.innerText = "⏳";

    const entryDiv = document.createElement("div");
    entryDiv.classList.add("chat-entry");
    entryDiv.innerHTML = `
      <div class="user">You:</div>
      <div class="text">${question}</div>
      <div class="bot">Bot:</div>
      <div class="text loading">Typing response...</div>
    `;
    historyDiv.appendChild(entryDiv);
    historyDiv.scrollTop = historyDiv.scrollHeight;

    try {
      const res = await fetch("/chatbot/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question })
      });
      const data = await res.json();
      const el = entryDiv.querySelector(".loading");
      el.textContent = data.answer;
      el.classList.remove("loading");
    } catch {
      const el = entryDiv.querySelector(".loading");
      el.textContent = "❌ Error sending the question.";
      el.classList.remove("loading");
    }

    inputField.value = "";
    inputField.disabled = false;
    sendBtn.disabled = false;
    sendBtn.innerText = "Send";
    inputField.focus();
  });
});

function toggleMaximize() {
  const popup = document.getElementById("chat-popup");
  const btn   = document.getElementById("maximizeBtn");
  const isMax = popup.classList.toggle("maximized");
  btn.textContent  = isMax ? "⤡" : "⤢";
  btn.title        = isMax ? "Minimize" : "Maximize";
  // scroll to bottom after resize
  setTimeout(() => {
    const h = document.getElementById("chat-history");
    if (h) h.scrollTop = h.scrollHeight;
  }, 260);
}