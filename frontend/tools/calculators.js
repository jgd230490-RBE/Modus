/* The haul calculators page (claude/tools-calculators, 17 Nov 2026). Plain script on top of the shared tools.js
   (WaysTools.call): each card's figures go to the open call, the answer printed is the one that comes back, and the
   PDF is made from the same figures by the same call, so the page and the file cannot disagree.
   Loaded BEFORE tools.js (the harness wants the shared script last); it only reaches WaysTools after the page has loaded. */
(function () {
  "use strict";
  var WAIT = 350;                                   // ms after the last keystroke before a card asks
  var SUM = "/api/tools/calculators/sum";
  var PDF = "/api/tools/calculators/pdf";
  var state = { which: "", seq: {} };

  function field(card, name) {
    var el = card.querySelector('[name="' + name + '"]');
    return el ? el.value : "";
  }

  var FIELDS = {
    lorries: { tonnes: "tonnes", lorry: "lorry", working_days: "working_days", round_trips: "round_trips" },
    carbon: { loads: "loads", miles: "miles", lorry: "lorry", way_back: "way_back" },
    surcharge: { diesel_then: "diesel_then", diesel_now: "diesel_now", share: "share", rate: "rate" }
  };

  function figures(card) {
    var which = card.getAttribute("data-which"), out = {}, map = FIELDS[which];
    for (var k in map) if (Object.prototype.hasOwnProperty.call(map, k)) out[k] = field(card, map[k]);
    return out;
  }

  function show(card, answer, detail, steps) {
    var v = card.querySelector(".ans .v"), s = card.querySelector(".ans small");
    v.textContent = answer || " ";
    s.textContent = detail || " ";
    var how = card.querySelector(".how");             // "How this was worked out": the server's own three steps, as text
    if (!how) return;
    var ol = how.querySelector("ol"), i, li;
    ol.textContent = "";
    for (i = 0; steps && i < steps.length; i++) {
      li = document.createElement("li");
      li.textContent = steps[i];
      ol.appendChild(li);
    }
    how.hidden = !(steps && steps.length);            // no answer, no fold; it stays open or closed as the person left it
  }

  function work(card) {
    var which = card.getAttribute("data-which");
    var sayEl = card.querySelector(".say");
    var n = (state.seq[which] = (state.seq[which] || 0) + 1);
    window.WaysTools.call(SUM, { which: which, figures: figures(card) }, sayEl).then(function (data) {
      if (n !== state.seq[which]) return;           // a newer figure has been typed since
      if (!data) { show(card, "", ""); return; }
      show(card, data.answer, data.detail, data.steps);
    });
  }

  function later(card) {
    var timer = null;
    return function () {
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () { work(card); }, WAIT);
    };
  }

  function download(name, b64) {
    var bin = atob(b64), bytes = new Uint8Array(bin.length), i;
    for (i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    var url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
    var a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  function done(on) {                                 // "Your PDF has downloaded." under the box, the box left open
    var el = document.querySelector("#pdfbox .done");
    if (el) el.hidden = !on;
  }

  function init() {
    var cards = document.querySelectorAll(".calc");
    var box = document.getElementById("pdfbox");
    var i;
    for (i = 0; i < cards.length; i++) {
      (function (card) {
        var go = later(card);
        card.addEventListener("input", go);
        card.addEventListener("change", go);
        var btn = card.querySelector(".pdf");
        if (btn) btn.addEventListener("click", function () {
          state.which = card.getAttribute("data-which");
          for (var j = 0; j < cards.length; j++) {          // the pressed card's button is the dark one, the others outline
            var b2 = cards[j].querySelector(".pdf");
            b2.className = "btn sm pdf " + (cards[j] === card ? "btn-ink" : "btn-line");
          }
          if (box) {
            box.setAttribute("data-col", String(Array.prototype.indexOf.call(cards, card) + 1));
            if (card.nextElementSibling !== box) card.parentNode.insertBefore(box, card.nextSibling);   // under the card on one column
            box.hidden = false;
            window.WaysTools.say(box.querySelector(".say"), "");
            done(false);                              // another card's PDF: the last download's line goes
            var email = box.querySelector('input[name="email"]');
            if (box.scrollIntoView) box.scrollIntoView({ block: "nearest", behavior: "smooth" });
            if (email) email.focus();
          }
        });
        work(card);
      })(cards[i]);
    }
    if (box) box.addEventListener("submit", function (e) {
      e.preventDefault();
      var sayEl = box.querySelector(".say");
      done(false);
      var card = document.getElementById("c-" + state.which);
      if (!card) { window.WaysTools.say(sayEl, "Pick a calculator first."); return; }
      window.WaysTools.call(PDF, {
        which: state.which,
        figures: figures(card),
        email: box.querySelector('input[name="email"]').value,
        news: box.querySelector('input[name="news"]').checked,
        website: box.querySelector('input[name="website"]').value
      }, sayEl).then(function (data) {
        if (!data) return;
        if (data.pdf) { download(data.filename || "wayscope.pdf", data.pdf); done(true); }
      });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
