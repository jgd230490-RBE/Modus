// ============================================================
//  Wayscope — corridor map configuration
//  Edit values here; no need to touch index.html.
// ============================================================
window.CONFIG = {
  // Mapbox public token. This is a browser (pk.) token and is safe to expose,
  // but you SHOULD restrict it by URL in your Mapbox account, and can rotate it here.
  MAPBOX_TOKEN: "pk.eyJ1IjoiamdkMjMwNDE5OTAiLCJhIjoiY211aDB1YTJtMHF3YzJ4cnpodTlsb2czOSJ9.B1oY8QnGB2YRBz0rV1klfg",

  // Where the forecast API lives. "/api" = same server that serves this map.
  API_BASE: "/api",

  // Forecast horizon (must match the backend). Month 1 = Jan of START_YEAR.
  START_YEAR: 2026,
  MONTH_COUNT: 60,

  // Unit the map paints forecasts in: "vehicles" | "t" | "m3"
  FORECAST_UNIT: "vehicles",

  // Theme (Wayscope, 29 Sep 2026): ink #1F2024, blue for routes/controls, orange is the
  // brand accent and is NOT used on the map (it would blur with amber warnings).
  // 24 Nov 2026 (John, the public map's route lines rethink, Q1 to Q4): the stock blues are gone from the map. The sign
  // blue is the one blue of a control, a pick and the forecast line with the heat map Off; a forecast line sits on a
  // WHITE casing on light grounds (index.html turns it pale on dark ones: HEAT_EDGE_DARK).
  COLORS: {
    brand:             "#0B4EA2",  // the sign blue (a picked route's halo, the shared sections before they take a colour)
    brandDark:         "#1F2024",  // ink (headings)
    forecast:          "#0B4EA2",  // the forecast line, heat map Off: one sign blue
    forecastCasing:    "#FFFFFF",  // the white casing under a forecast line (light grounds)
    selection:         "#DC2626",  // a clicked/selected route
    peak:              "#DC2626",  // alerts / peak values (theme red)
    green:             "#059669"   // success / confirmations
  }
};
