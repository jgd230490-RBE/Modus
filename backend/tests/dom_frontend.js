/*
 * dom_frontend.js — the staff app mounted in a REAL DOM (jsdom), for the behaviour the
 * static harnesses cannot see: clicks, state, what ends up on <html>, what is stored.
 *
 * 5 Oct 2026, written for the Appearance picker. render_frontend.js renders components
 * to static markup; parse_frontend.js reads the source. Neither can open a popover.
 *
 * Needs: typescript, react, react-dom, jsdom — resolved through NODE_PATH (or a
 * node_modules on the path), like the other JS harnesses:
 *     npm install -g typescript@5 react@18 react-dom@18 jsdom@24
 *     export NODE_PATH="$(npm root -g)"; node backend/tests/dom_frontend.js
 * Without jsdom it prints SKIPPED and exits 0, so the suite stays runnable.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("dom_frontend.js: SKIPPED — jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;

const dom = new JSDOM(`<!doctype html><html><head><meta name="theme-color" content="#1F2024"></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.mapboxgl = { Map: function(){ return { on(){}, remove(){}, getCanvas: () => ({ style: {} }), addControl(){}, getSource: () => null, getLayer: () => null, resize(){}, setStyle(){}, fitBounds(){} }; }, accessToken: "", NavigationControl: function(){}, ScaleControl: function(){} };
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
const click = (el) => act(() => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });

// ---- 1. a remembered choice is applied before anything mounts -------------------------
w.localStorage.setItem("modus_theme", "light");
w.eval(js + "\nwindow.__T = THEME;");   // the store is a const in the script scope; expose it for §3
ok("APPEARANCE: a remembered look (localStorage modus_theme) is on <html> before React mounts",
   w.document.documentElement.getAttribute("data-theme") === "light");
ok("APPEARANCE: theme-color follows the header colour (white for the light look)",
   w.document.querySelector('meta[name="theme-color"]').getAttribute("content") === "#FFFFFF");

// ---- 2. the picker in the header ------------------------------------------------------
act(() => { w.ReactDOM.createRoot(w.document.getElementById("root")).render(
  w.React.createElement(w.Header, { view: "portal", role: { label: "Admin", ipt: null }, setView(){}, signOut(){}, vehLang: "en", setVehLang(){} })); });
const btn = w.document.querySelector(".appearance-btn");
ok("APPEARANCE: one 32 px button in the header, closed, labelled, before Sign out",
   !!btn && btn.closest("header") !== null && btn.getAttribute("aria-expanded") === "false" && btn.getAttribute("aria-label") === "Appearance"
   && [...w.document.querySelectorAll("header button")].findIndex(b => b === btn) < [...w.document.querySelectorAll("header button")].findIndex(b => /Sign out/.test(b.textContent)));
ok("APPEARANCE: nothing is open until it is clicked", !w.document.querySelector(".appearance-menu"));
click(btn);
const items = [...w.document.querySelectorAll(".appearance-item")];
ok("APPEARANCE: the popover lists Ink, Light, Dark as menuitemradio, the current one checked",
   items.map(b => b.textContent.replace("✓", "").trim()).join("|") === "Ink|Light|Dark"
   && items.map(b => b.getAttribute("aria-checked")).join("|") === "false|true|false" && btn.getAttribute("aria-expanded") === "true");
click(items[2]);
ok("APPEARANCE: choosing Dark sets html[data-theme=dark], stores it, closes the popover, ink theme-color",
   w.document.documentElement.getAttribute("data-theme") === "dark" && w.localStorage.getItem("modus_theme") === "dark"
   && !w.document.querySelector(".appearance-menu") && w.document.querySelector('meta[name="theme-color"]').getAttribute("content") === "#1F2024");
click(btn);
act(() => { w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
ok("APPEARANCE: Escape closes it", !w.document.querySelector(".appearance-menu"));
click(btn);
act(() => { w.document.body.dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true })); });
ok("APPEARANCE: a click outside closes it", !w.document.querySelector(".appearance-menu"));
click(btn);
act(() => { btn.dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true })); });
ok("APPEARANCE: a click on the button itself does not count as outside", !!w.document.querySelector(".appearance-menu"));
click(items[0] === undefined ? btn : [...w.document.querySelectorAll(".appearance-item")][0]);
ok("APPEARANCE: back to Ink", w.document.documentElement.getAttribute("data-theme") === "ink" && w.localStorage.getItem("modus_theme") === "ink");
act(() => { w.applyTheme("bogus"); });
ok("APPEARANCE: an unknown value falls back to ink", w.document.documentElement.getAttribute("data-theme") === "ink");

// ---- 3. subscribers ---------------------------------------------------------------------
let seen = [];
w.__T.subs.add((n) => seen.push(n));
act(() => { w.applyTheme("dark"); w.applyTheme("light"); });
ok("APPEARANCE: subscribers (the charts) hear every change in order", seen.join("|") === "dark|light");

console.log(`\n${pass} passed, ${fail.length} failed`);
fail.forEach(f => console.log("  FAIL: " + f));
process.exit(fail.length ? 1 : 0);
