// Global scan capture — the "parasitic" core.
//
// A keyboard-wedge barcode scanner (the Eyoyo EY-H2) types the code as
// keystrokes into whatever app has focus. We listen GLOBALLY (uiohook-napi),
// so we see the same keystrokes the pharmacist's real app (Farmakon) receives —
// without stealing focus and without the scanner needing to point at us.
//
// This is NOT a general keylogger: we only reconstruct a string when the
// keystrokes arrive scanner-fast (each within `interKeyMs` of the last) AND end
// in Enter AND clear a minimum length. Human typing is far slower, so it resets
// the buffer and is never assembled or emitted. For a hard guarantee in
// production, program the Eyoyo with a sentinel prefix and set `sentinelPrefix`
// — then only sentinel-framed bursts are ever considered.

const { uIOhook, UiohookKey } = require("uiohook-napi");

// Build keycode → character for the alphanumeric set barcodes use. Case is
// dropped (barcode payloads here are uppercase; we upper-case the result), so
// Shift state is irrelevant — simpler and robust.
function buildKeymap() {
  const map = {};
  for (let c = 65; c <= 90; c++) {
    const L = String.fromCharCode(c); // A..Z
    if (UiohookKey[L] != null) map[UiohookKey[L]] = L;
  }
  for (let d = 0; d <= 9; d++) {
    const s = String(d);
    if (UiohookKey[s] != null) map[UiohookKey[s]] = s;
    if (UiohookKey["Numpad" + d] != null) map[UiohookKey["Numpad" + d]] = s;
  }
  if (UiohookKey.Minus != null) map[UiohookKey.Minus] = "-";
  if (UiohookKey.Slash != null) map[UiohookKey.Slash] = "/";
  return map;
}

function startScanner(scanCfg, onScan) {
  const KEY = buildKeymap();
  const ENTER = UiohookKey.Enter;
  const maxGap = scanCfg.interKeyMs || 120;
  const minLen = scanCfg.minLength || 4;
  const prefix = scanCfg.sentinelPrefix || "";

  let buf = "";
  let last = 0;

  uIOhook.on("keydown", (e) => {
    const now = Date.now();

    if (e.keycode === ENTER) {
      // A scan terminates in Enter. buf only ever holds a fast contiguous burst
      // (a slow gap wipes it below), so a non-empty buf here IS a scan.
      if (buf.length >= minLen && now - last <= maxGap * 4) {
        let code = buf;
        buf = "";
        if (prefix) {
          if (!code.startsWith(prefix)) return; // not a sentinel-framed scan
          code = code.slice(prefix.length);
        }
        if (code.length >= minLen) onScan(code.toUpperCase());
        return;
      }
      buf = "";
      return;
    }

    // A slow gap between keys means this isn't (or is no longer) a scan burst —
    // start fresh. Human typing lands here every keystroke and never assembles.
    if (now - last > maxGap) buf = "";

    // Accumulate payload chars. Unmapped keys (GS1 FNC1/group separators,
    // punctuation a DataMatrix pack emits) are SKIPPED, not reset — so scanning
    // a real medicine pack still yields a stable alphanumeric string (GTIN +
    // serial + lot), which the agent maps to a demo prescription.
    const ch = KEY[e.keycode];
    if (ch != null) buf += ch;
    last = now;
  });

  uIOhook.start();
  return () => uIOhook.stop();
}

module.exports = { startScanner };
