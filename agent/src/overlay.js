// Overlay renderer. Pure display: turns IPC messages from the main process into
// the idle pill / checking / result card / error states.

const $ = (id) => document.getElementById(id);
const app = $("app");
const pill = $("pill");
const dot = $("dot");
const pillText = $("pill-text");
const card = $("card");

const RANK = { block: 3, review: 2, ok: 1 };
let hideTimer = null;
let autoHideMs = 20000;

// Ask the main process to size the window to exactly the current content, after
// layout settles — so a long card never clips and the idle pill leaves no big
// invisible window. Runs on every state change.
function fit() {
  requestAnimationFrame(() => {
    const el = card.classList.contains("hidden") ? pill : card;
    const h = Math.ceil(el.getBoundingClientRect().height) + 16; // + #app padding
    window.agent.resize(h);
  });
}

function showPill(text, cls) {
  card.classList.add("hidden");
  pill.classList.remove("hidden");
  pillText.textContent = text;
  dot.className = "dot" + (cls ? " " + cls : "");
  fit();
}

function worst(checks) {
  return (checks || []).reduce((w, c) => (RANK[c.status] > RANK[w] ? c.status : w), "ok");
}

function renderResult(rx) {
  const checks = (rx.safetyChecks || [])
    .slice()
    .sort((a, b) => (RANK[b.status] || 0) - (RANK[a.status] || 0));
  const top = worst(checks);

  pill.classList.add("hidden");
  card.classList.remove("hidden");
  card.className = "card edge-" + top;

  $("badge").className = "badge " + top;
  $("badge").textContent = top === "block" ? "Do not dispense" : top === "review" ? "Review" : "Clear";
  $("rx").textContent = rx.rxId || rx.code || "";

  const p = rx.patient || {};
  $("who").textContent = [p.name, p.age ? p.age + "y" : null].filter(Boolean).join(" · ");
  const med = rx.medication || {};
  $("drug").textContent = [med.name || med.commercialName, med.strength, med.atcCode]
    .filter(Boolean)
    .join(" · ");

  const ul = $("checks");
  ul.innerHTML = "";
  for (const c of checks) {
    const li = document.createElement("li");
    li.innerHTML =
      `<span class="cdot ${c.status}"></span>` +
      `<div class="cbody"><div class="cname">${c.name || c.checkType || ""}</div>` +
      `<div class="cmsg">${c.message || ""}</div></div>`;
    ul.appendChild(li);
  }

  fit();
  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => showPill("Listening for scans", "ok"), autoHideMs);
}

window.agent.onStatus((s) => {
  if (typeof s.autoHideMs === "number") autoHideMs = s.autoHideMs;
  showPill(s.text, s.ok ? "ok" : "err");
});
window.agent.onChecking((code) => showPill("Checking " + code + "…", "busy"));
window.agent.onResult((rx) => renderResult(rx));
window.agent.onError((d) => {
  showPill(d.message || "Scan error", "err");
  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => showPill("Listening for scans", "ok"), 6000);
});
window.agent.onClear(() => showPill("Listening for scans", "ok"));
