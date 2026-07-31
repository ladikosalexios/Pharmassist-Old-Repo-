// Main-process backend client for the mock PharmAssist API.
//
// Runs in Electron's MAIN process (Node), NOT a renderer — so there is no
// browser CORS / SameSite enforcement, and the session cookie never touches
// the overlay window. Auth is the same httpOnly cookie the SPA uses: log in
// once, capture `pharmassist_session`, resend it on every call.

class Backend {
  constructor(cfg) {
    this.base = cfg.backendUrl.replace(/\/$/, "");
    this.creds = cfg.login;
    this.cookie = null;
  }

  _captureCookie(res) {
    // undici (Electron/Node fetch) splits Set-Cookie via getSetCookie().
    const cookies = res.headers.getSetCookie
      ? res.headers.getSetCookie()
      : [res.headers.get("set-cookie")].filter(Boolean);
    for (const c of cookies) {
      const m = /pharmassist_session=[^;]+/.exec(c || "");
      if (m) this.cookie = m[0];
    }
  }

  async _fetch(path, opts = {}) {
    const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    if (this.cookie) headers.Cookie = this.cookie;
    const res = await fetch(this.base + path, {
      method: opts.method || "GET",
      headers,
      body: opts.body,
    });
    this._captureCookie(res);
    return res;
  }

  async login() {
    const res = await this._fetch("/auth/login", {
      method: "POST",
      body: JSON.stringify(this.creds),
    });
    if (!res.ok) {
      let detail = "";
      try {
        detail = (await res.json()).detail || "";
      } catch {
        /* ignore */
      }
      throw new Error(`login failed (${res.status})${detail ? ": " + detail : ""}`);
    }
    return true;
  }

  // Resolve a scanned code to a prescription + its safety checks. In mock mode
  // the code IS the rx_id (e.g. RX2024-005). Re-auths once on a 401.
  async prescription(code, _retried = false) {
    const res = await this._fetch("/prescriptions/" + encodeURIComponent(code));
    if (res.status === 401 && !_retried) {
      await this.login();
      return this.prescription(code, true);
    }
    // 404 = no such prescription; 422 = the code isn't a valid ΗΔΥΚΑ barcode
    // (e.g. a scanned medicine pack in live mode). Both mean "nothing to review"
    // — surface an honest not-found rather than an error.
    if (res.status === 404 || res.status === 422) return { notFound: true, code };
    if (!res.ok) throw new Error(`prescription ${code} → ${res.status}`);
    return res.json();
  }
}

module.exports = { Backend };
