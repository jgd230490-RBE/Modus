/* Wayscope tools: the one small script every public tool page shares (claude/tools-shell, 16 Nov 2026).
   Plain script, no framework, nothing loaded from outside the app.

   WaysTools.call(path, body, sayEl) -> Promise of the answer's JSON, or null.
     POSTs `body` as JSON to an open call under /api/tools/. It never sends a cookie (credentials "omit"): a tool call
     reads nothing of anyone's plan and needs no sign-in. On any failure it writes ONE plain sentence into `sayEl`
     (give it the page's <p class="say" role="status"> box) and returns null: the server's own sentence when the
     refusal carries one ({"detail": {"say": "…"}}, tools_public.refuse), else a general one. Never a status number,
     never the raw reply; the raw reply goes to the console only, as the app does ("Wayscope:").
   WaysTools.say(sayEl, words)  -> writes or clears that sentence. */
(function () {
  "use strict";
  var GENERAL = "That did not work. Please try again in a minute.";
  var OFFLINE = "The page could not reach Wayscope. Check the connection and try again.";

  function say(el, words) {
    if (el) el.textContent = words || "";
  }

  function call(path, body, sayEl) {
    say(sayEl, "");
    if (typeof path !== "string" || path.indexOf("/api/tools/") !== 0) {
      say(sayEl, GENERAL);
      return Promise.resolve(null);
    }
    return fetch(path, {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "Accept": "application/json", "X-Wayscope": "1" },
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (r.ok && data !== null) return data;
        var words = data && data.detail && typeof data.detail === "object" && typeof data.detail.say === "string"
          ? data.detail.say : GENERAL;
        if (window.console) console.warn("Wayscope:", path, r.status, text.slice(0, 300));
        say(sayEl, words);
        return null;
      });
    }, function (e) {
      if (window.console) console.warn("Wayscope:", path, e);
      say(sayEl, OFFLINE);
      return null;
    });
  }

  window.WaysTools = { call: call, say: say, GENERAL: GENERAL, OFFLINE: OFFLINE };
})();
