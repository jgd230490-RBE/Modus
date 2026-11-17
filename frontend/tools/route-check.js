/* The route check request form (claude/tools-route-check-request, 16 Nov 2026).
   Sends the typed boxes to the open call and shows the thanks block; the shared script says any failure in one sentence. */
(function () {
  "use strict";
  var form = document.getElementById("rc-form");
  if (!form) return;
  var thanks = document.getElementById("rc-thanks");
  var say = form.querySelector(".say");
  var busy = false;

  function val(name) {
    var el = form.elements[name];
    return el ? String(el.value || "").trim() : "";
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (busy) return;
    busy = true;
    var body = {
      from: val("from"), to: val("to"), lorry: val("lorry"), loads: val("loads"),
      name: val("name"), email: val("email"), company: val("company"), note: val("note"),
      website: String(form.elements.website.value || "")
    };
    window.WaysTools.call("/api/tools/route-check/request", body, say).then(function (data) {
      busy = false;
      if (!data) return;
      var go = form.querySelector('button[type="submit"]');
      if (go) go.disabled = true;
      thanks.hidden = false;
      if (thanks.scrollIntoView) thanks.scrollIntoView({ block: "nearest" });
    });
  });
})();
