// ============================================================
//  Modus — corridor map configuration
//  Edit values here; no need to touch index.html.
// ============================================================
window.CONFIG = {
  // Mapbox public token. This is a browser (pk.) token and is safe to expose,
  // but you SHOULD restrict it by URL in your Mapbox account, and can rotate it here.
  MAPBOX_TOKEN: "pk.eyJ1IjoiamdkMjMwNDE5OTAiLCJhIjoiY21xbnJzaTRrMDYyOTJxcXowczRxNTlxdyJ9.xujuSc3O8RcgKIitWNGIWg",

  // Where the forecast API lives. "/api" = same server that serves this map.
  API_BASE: "/api",

  // Forecast horizon (must match the backend). Month 1 = Jan of START_YEAR.
  START_YEAR: 2026,
  MONTH_COUNT: 60,

  // Unit the map paints forecasts in: "vehicles" | "t" | "m3"
  FORECAST_UNIT: "vehicles",

  // Theme (Modus). Change a hex here to restyle the map.
  COLORS: {
    brand:             "#2563EB",  // the accent blue
    brandDark:         "#0F172A",  // ink (headings, casing)
    forecast:          "#3B82F6",  // forecast route highlight (core)
    forecastCasing:    "#0F172A",  // darker outline behind forecast routes
    forecastLabelHalo: "#2563EB",  // halo behind forecast labels
    selection:         "#DC2626",  // a clicked/selected route
    peak:              "#DC2626",  // alerts / peak values (theme red)
    green:             "#059669"   // success / confirmations
  }
};
