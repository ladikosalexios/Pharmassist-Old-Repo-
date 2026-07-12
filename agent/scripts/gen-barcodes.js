// Generate a printable page of Code-128 barcodes for the mock demo
// prescriptions. Scan any with the Eyoyo → the agent resolves it to that
// prescription's curated safety checks. Run: npm run barcodes → open barcodes.html.

const bwipjs = require("bwip-js");
const fs = require("fs");
const path = require("path");

// rx_ids that have curated MOCK_SAFETY_CHECKS (backend/app/services/safety_checks.py).
const CODES = [
  ["RX2024-001", "clear-ish"],
  ["RX2024-002", ""],
  ["RX2024-003", ""],
  ["RX2024-005", "Warfarin — BLOCK (amiodarone) + review (aspirin)"],
  ["RX2024-006", ""],
  ["RX2024-007", ""],
  ["RX2024-008", ""],
  ["RX2024-009", ""],
];

(async () => {
  let cards = "";
  for (const [code, note] of CODES) {
    const svg = bwipjs.toSVG({
      bcid: "code128",
      text: code,
      scale: 3,
      height: 12,
      includetext: true,
      textxalign: "center",
    });
    cards += `<div class="card"><h3>${code}</h3>${svg}${note ? `<p class="note">${note}</p>` : ""}</div>`;
  }
  const html = `<!doctype html><html><head><meta charset="utf-8" />
<title>PharmAssist — test barcodes</title>
<style>
  body { font-family: system-ui, sans-serif; padding: 28px; color: #1a1f2b; }
  h1 { font-size: 20px; }
  p.lead { color: #556; max-width: 640px; }
  .grid { display: flex; flex-wrap: wrap; gap: 18px; margin-top: 18px; }
  .card { border: 1px solid #dce0e8; border-radius: 10px; padding: 16px; text-align: center; width: 300px; }
  .card h3 { margin: 0 0 8px; font-family: ui-monospace, monospace; }
  .card svg { width: 260px; height: auto; }
  .note { font-size: 12px; color: #8a94a6; margin: 8px 0 0; }
</style></head><body>
<h1>PharmAssist — test prescription barcodes</h1>
<p class="lead">Scan any barcode with the Eyoyo (keyboard-wedge mode) while the PharmAssist Agent is running. Each maps to a mock prescription and its curated safety checks. Print this page or scan straight off the screen.</p>
<div class="grid">${cards}</div>
</body></html>`;

  const out = path.join(__dirname, "..", "barcodes.html");
  fs.writeFileSync(out, html);
  console.log("wrote", out, "with", CODES.length, "barcodes");
})();
