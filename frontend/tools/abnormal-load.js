/* The abnormal load adviser's free check (claude/tools-abnormal-adviser, 17 Nov 2026).
   Card 3 of the agreed mockup draws no button: the answer is asked for once every box it needs is filled, and again a
   moment after any change. The words come from the server (backend/tools_abnormal.py); this script only lays them out,
   as text (never as HTML). Nothing is kept: no cookie, no storage. */
(function () {
  "use strict";
  var form = document.getElementById("adv-form");
  var res = document.getElementById("adv-res");
  if (!form || !res) return;
  var sayBox = form.querySelector(".say");
  var NEEDED = ["width_m", "length_m", "height_m", "gross_t", "max_axle_t", "axle_count", "date"];
  var timer = null;
  var asked = 0;

  function val(name) {
    var el = form.elements[name];
    return el ? String(el.value || "").trim() : "";
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function draw(p) {
    res.textContent = "";
    var big = el("div", "big");
    big.appendChild(el("span", "v", p.head));
    (p.chips || []).forEach(function (c) { big.appendChild(el("span", "chip " + c[0], c[1])); });
    res.appendChild(big);
    if (p.over && p.over.length) {
      var o = el("p", "note", "Over the normal limits: " + p.over.join(", ") + ".");
      o.style.margin = "0";
      res.appendChild(o);
    }
    (p.notes || []).forEach(function (n) {
      var q = el("p", "note", n);
      q.style.margin = "6px 0 0";
      q.style.color = "var(--ink-2)";
      res.appendChild(q);
    });
    if (p.rows && p.rows.length) {
      var ul = el("ul", "adv");
      p.rows.forEach(function (r) {
        var li = el("li");
        li.appendChild(el("b", null, r[0]));
        li.appendChild(el("span", null, r[1]));
        ul.appendChild(li);
      });
      res.appendChild(ul);
    }
    (p.fine || []).forEach(function (f) { res.appendChild(el("p", "fine2", f)); });
    var next = el("div", "next");
    var span = el("span");
    span.appendChild(el("b", null, p.next[0]));
    span.appendChild(document.createTextNode(" " + p.next[1]));
    next.appendChild(span);
    var a = el("a", "btn btn-line sm", "See the platform");
    a.href = "https://wayscope.co.uk/";
    next.appendChild(a);
    res.appendChild(next);
    res.appendChild(el("p", "fine2", p.last));
    res.hidden = false;
  }

  function ask() {
    var missing = NEEDED.filter(function (n) { return !val(n); });
    if (missing.length) {
      res.hidden = true;
      WaysTools.say(sayBox, "");
      return;
    }
    var body = {
      width_m: val("width_m"), length_m: val("length_m"), height_m: val("height_m"), gross_t: val("gross_t"),
      max_axle_t: val("max_axle_t"), axle_count: val("axle_count"), date: val("date"),
      where: val("where") || "england-and-wales", axle_spacings_m: val("axle_spacings_m"),
      indivisible: !!(form.elements.indivisible && form.elements.indivisible.checked),
      cu_vehicle: !!(form.elements.cu_vehicle && form.elements.cu_vehicle.checked),
      axle_driving: !!(form.elements.axle_driving && form.elements.axle_driving.checked), website: val("website")
    };
    var mine = ++asked;
    WaysTools.call("/api/tools/abnormal-load", body, sayBox).then(function (data) {
      if (mine !== asked) return;              // a later change has asked again
      if (!data || !data.page) { res.hidden = true; return; }
      draw(data.page);
    });
  }

  function soon() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(ask, 500);
  }

  form.addEventListener("input", soon);
  form.addEventListener("change", soon);
  form.addEventListener("submit", function (e) { e.preventDefault(); ask(); });
})();
