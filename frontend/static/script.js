/**
 * FareLens — Interactive Airfare Intelligence Client
 */
document.addEventListener("DOMContentLoaded", () => {
  let catalogData = null;
  let lastPredictionResult = null;
  let lastPayload = null;

  const toastEl = document.getElementById("toast");
  const fareForm = document.getElementById("fare-form");
  const sourceEl = document.getElementById("source");
  const destEl = document.getElementById("destination");
  const airlineEl = document.getElementById("airline");
  const stopsEl = document.getElementById("total_stops");
  const routeEl = document.getElementById("route_select");
  const infoEl = document.getElementById("additional_info");
  const dateEl = document.getElementById("journey_date");
  const depEl = document.getElementById("dep_time");
  const arrEl = document.getElementById("arrival_time");
  const inflationEl = document.getElementById("inflation_factor");
  const notesEl = document.getElementById("trip_notes");
  const btnSubmit = document.getElementById("btn-submit");
  const btnSaveAlert = document.getElementById("btn-save-alert");

  const airportCodes = {
    Banglore: { code: "BLR", name: "Bangalore" },
    Delhi: { code: "DEL", name: "Delhi" },
    "New Delhi": { code: "DEL", name: "New Delhi" },
    Kolkata: { code: "CCU", name: "Kolkata" },
    Chennai: { code: "MAA", name: "Chennai" },
    Mumbai: { code: "BOM", name: "Mumbai" },
    Cochin: { code: "COK", name: "Cochin" },
    Hyderabad: { code: "HYD", name: "Hyderabad" },
  };

  function escapeHtml(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function showToast(msg, isError = false) {
    toastEl.textContent = msg;
    toastEl.className = `toast show${isError ? " error" : ""}`;
    setTimeout(() => {
      toastEl.className = "toast";
    }, 3200);
  }

  function fmtInr(num) {
    return Number(num || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }

  async function apiFetch(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    const resp = await fetch(url, { ...options, headers });
    const isJson = (resp.headers.get("content-type") || "").includes("application/json");
    const data = isJson ? await resp.json() : await resp.text();
    if (!resp.ok) {
      const errMsg = typeof data === "object" && data.detail ? data.detail : `HTTP ${resp.status}`;
      throw new Error(errMsg);
    }
    return data;
  }

  // ---------------------- Tab Switching ----------------------
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const target = document.getElementById(btn.dataset.tab);
      if (target) target.classList.add("active");

      if (btn.dataset.tab === "tab-crud") {
        loadHistory();
        loadAlerts();
      } else if (btn.dataset.tab === "tab-admin") {
        loadDbStudio();
      }
    });
  });

  // ---------------------- Form & Route Sync ----------------------
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  dateEl.value = tomorrow.toISOString().split("T")[0];

  function updateDuration() {
    if (!depEl.value || !arrEl.value) return;
    const [dh, dm] = depEl.value.split(":").map(Number);
    const [ah, am] = arrEl.value.split(":").map(Number);
    let diff = ah * 60 + am - (dh * 60 + dm);
    if (diff <= 0) diff += 24 * 60;
    document.getElementById("duration-preview-text").textContent = `${Math.floor(diff / 60)}h ${diff % 60}m`;
  }

  function updateRouteVisualizer() {
    const src = airportCodes[sourceEl.value] || { code: "SRC", name: sourceEl.value };
    const dst = airportCodes[destEl.value] || { code: "DST", name: destEl.value };
    document.querySelector(".origin-preview").textContent = src.code;
    document.querySelector(".origin-name").textContent = src.name;
    document.querySelector(".dest-preview").textContent = dst.code;
    document.querySelector(".dest-name").textContent = dst.name;
    populateMatchingRoutes();
  }

  function populateMatchingRoutes() {
    if (!catalogData) return;
    const key = `${sourceEl.value}|${destEl.value}|${stopsEl.value}`;
    const matches = (catalogData.routes_by_trip && catalogData.routes_by_trip[key]) || [];
    routeEl.innerHTML = '<option value="auto">Auto-select typical route</option>';
    matches.slice(0, 12).forEach((item) => {
      const opt = document.createElement("option");
      opt.value = item.route;
      opt.textContent = `${item.route} (${item.sample_count} historical flights)`;
      routeEl.appendChild(opt);
    });
    document.getElementById("route-hint-text").textContent = matches.length
      ? `${matches.length} layover paths available`
      : "Direct/standard path";
  }

  sourceEl.addEventListener("change", updateRouteVisualizer);
  destEl.addEventListener("change", updateRouteVisualizer);
  stopsEl.addEventListener("change", populateMatchingRoutes);
  depEl.addEventListener("input", updateDuration);
  arrEl.addEventListener("input", updateDuration);

  // ---------------------- Estimator & Batch Comparisons ----------------------
  function currentPayload() {
    return {
      airline: airlineEl.value,
      source: sourceEl.value,
      destination: destEl.value,
      journey_date: dateEl.value,
      dep_time: depEl.value,
      arrival_time: arrEl.value,
      total_stops: parseInt(stopsEl.value, 10),
      route: routeEl.value || "auto",
      additional_info: infoEl.value || "No info",
      inflation_factor: parseFloat(inflationEl.value || "1.0"),
      notes: notesEl.value || "",
    };
  }

  function badgeClass(cat) {
    if (cat === "Budget") return "badge-budget";
    if (cat === "Standard") return "badge-standard";
    if (cat === "Premium") return "badge-premium";
    return "badge-surge";
  }

  async function runPredictionAndComparisons() {
    const payload = currentPayload();
    if ((airportCodes[payload.source]?.code || payload.source) === (airportCodes[payload.destination]?.code || payload.destination)) {
      showToast("Origin and destination refer to the same city. Choose two different airports.", true);
      return;
    }

    btnSubmit.disabled = true;
    btnSubmit.textContent = "Calculating Fare & Comparing Options...";
    try {
      const [predRes, dateRes, airlineRes] = await Promise.all([
        apiFetch("/api/predict", { method: "POST", body: JSON.stringify(payload) }),
        apiFetch("/api/compare-dates", { method: "POST", body: JSON.stringify(payload) }),
        apiFetch("/api/compare-airlines", { method: "POST", body: JSON.stringify(payload) }),
      ]);

      lastPredictionResult = predRes;
      lastPayload = payload;
      btnSaveAlert.disabled = false;
      renderPredictionCard(predRes);
      renderFlexDates(dateRes);
      renderAirlineComparisons(airlineRes);
    } catch (err) {
      showToast(err.message, true);
    } finally {
      btnSubmit.disabled = false;
      btnSubmit.textContent = "Estimate Fare & Compare Options";
    }
  }

  function renderPredictionCard(res) {
    document.getElementById("price-display").textContent = fmtInr(res.predicted_fare);
    document.getElementById("price-range-pill").textContent =
      `Typical Fare Band: ₹${fmtInr(res.confidence_interval.lower)} – ₹${fmtInr(res.confidence_interval.upper)}`;
    const badge = document.getElementById("fare-tier-badge");
    badge.textContent = `${res.fare_category} Fare`;
    badge.className = `badge ${badgeClass(res.fare_category)}`;
    document.getElementById("price-caption-text").textContent =
      `Estimated single-passenger fare • Saved as search #${res.prediction_id}`;

    document.getElementById("summary-airline").textContent = res.flight_details.airline;
    document.getElementById("summary-route").textContent = res.flight_details.resolved_route_path;
    document.getElementById("summary-duration").textContent = `${res.flight_details.duration} • ${res.flight_details.stops}`;
    document.getElementById("summary-info").textContent = res.flight_details.additional_info;
    document.getElementById("summary-base-fare").textContent = `₹${fmtInr(res.historical_2019_fare)} (${res.inflation_factor}x)`;

    const driversWrap = document.getElementById("drivers-wrap");
    driversWrap.innerHTML = res.drivers
      .map((d) => `<span class="driver-chip ${escapeHtml(d.tone)}"><strong>${escapeHtml(d.factor)}:</strong> ${escapeHtml(d.impact)}</span>`)
      .join("");
  }

  function renderFlexDates(res) {
    const grid = document.getElementById("flex-dates-grid");
    document.getElementById("flex-date-summary").textContent =
      `Cheapest day: ${res.cheapest_date} (₹${fmtInr(res.cheapest_fare)})`;
    document.getElementById("flex-savings-badge").textContent =
      res.potential_savings > 0 ? `Save up to ₹${fmtInr(res.potential_savings)}` : "Optimal Date Selected";

    grid.innerHTML = res.dates
      .map((d) => {
        const cls = d.date === res.cheapest_date ? "cheapest" : d.is_selected ? "active" : "";
        return `
          <button type="button" class="date-tile ${cls}" data-date="${escapeHtml(d.date)}">
            <span class="d-day">${escapeHtml(d.label)}</span>
            <span class="d-price">₹${fmtInr(d.predicted_fare)}</span>
          </button>`;
      })
      .join("");

    grid.querySelectorAll(".date-tile").forEach((tile) => {
      tile.addEventListener("click", () => {
        dateEl.value = tile.dataset.date;
        runPredictionAndComparisons();
      });
    });
  }

  function renderAirlineComparisons(res) {
    const container = document.getElementById("airline-compare-bars");
    const maxFare = Math.max(...res.comparisons.map((c) => c.predicted_fare), 1);
    container.innerHTML = res.comparisons
      .map((c) => {
        const pct = Math.round((c.predicted_fare / maxFare) * 100);
        const fillCls = c.is_selected ? "emerald" : "";
        return `
          <div class="bar-row">
            <span class="bar-label">${escapeHtml(c.airline)}${c.is_selected ? " ★" : ""}</span>
            <div class="bar-track"><div class="bar-fill ${fillCls}" style="width:${pct}%"></div></div>
            <span class="bar-val">₹${fmtInr(c.predicted_fare)}</span>
          </div>`;
      })
      .join("");
  }

  fareForm.addEventListener("submit", (e) => {
    e.preventDefault();
    runPredictionAndComparisons();
  });

  btnSaveAlert.addEventListener("click", async () => {
    if (!lastPredictionResult || !lastPayload) return;
    const defaultTarget = Math.round(lastPredictionResult.predicted_fare * 0.9);
    const input = window.prompt("Enter your target alert fare (INR):", String(defaultTarget));
    if (!input) return;
    const targetPrice = parseFloat(input);
    if (Number.isNaN(targetPrice) || targetPrice <= 0) {
      showToast("Invalid target price.", true);
      return;
    }
    try {
      await apiFetch("/api/alerts", {
        method: "POST",
        body: JSON.stringify({
          prediction_id: lastPredictionResult.prediction_id,
          airline: lastPayload.airline,
          source: lastPayload.source,
          destination: lastPayload.destination,
          journey_date: lastPayload.journey_date,
          target_price: targetPrice,
          estimated_price: lastPredictionResult.predicted_fare,
          notes: lastPayload.notes || "Saved from Fare Estimator",
        }),
      });
      showToast("Saved to Price Watchlist!");
      loadAlerts();
    } catch (err) {
      showToast(err.message, true);
    }
  });

  // ---------------------- EDA Insights Loader ----------------------
  function renderBarList(elId, items, labelKey, valKey, suffix = "", prefix = "₹", fillCls = "") {
    const el = document.getElementById(elId);
    if (!el || !items || !items.length) return;
    const maxVal = Math.max(...items.map((i) => Number(i[valKey])), 1);
    el.innerHTML = items
      .map((item) => {
        const val = Number(item[valKey]);
        const pct = Math.max(4, Math.round((val / maxVal) * 100));
        return `
          <div class="bar-row">
            <span class="bar-label" title="${escapeHtml(item[labelKey])}">${escapeHtml(item[labelKey])}</span>
            <div class="bar-track"><div class="bar-fill ${fillCls}" style="width:${pct}%"></div></div>
            <span class="bar-val">${prefix}${fmtInr(val)}${suffix}</span>
          </div>`;
      })
      .join("");
  }

  async function loadAnalytics() {
    const analyticsRes = await apiFetch("/api/analytics");
    const eda = analyticsRes.eda || {};
    const ov = eda.dataset_overview || {};
    document.getElementById("eda-kpis").innerHTML = `
      <div class="kpi-card"><div class="label">Cleaned Records</div><div class="value">${fmtInr(ov.cleaned_records)}</div><div class="sub">${ov.duplicates_removed || 220} duplicates removed</div></div>
      <div class="kpi-card"><div class="label">Mean / Median Fare</div><div class="value">₹${fmtInr(ov.mean_price)}</div><div class="sub">Median: ₹${fmtInr(ov.median_price)}</div></div>
      <div class="kpi-card"><div class="label">Fare Range</div><div class="value">₹${fmtInr(ov.min_price)}</div><div class="sub">Max Business: ₹${fmtInr(ov.max_price)}</div></div>
      <div class="kpi-card"><div class="label">Within ±₹1,000</div><div class="value">${ov.within_1000_inr_pct || 0}%</div><div class="sub">Within ±₹1,500: ${ov.within_1500_inr_pct || 0}%</div></div>
    `;

    renderBarList("eda-importances", (eda.feature_importances || []).slice(0, 8), "feature", "importance_pct", "%", "", "emerald");
    renderBarList("eda-airlines", (eda.by_airline || []).slice(0, 8), "airline", "mean_price");
    renderBarList("eda-stops", eda.by_stops || [], "label", "mean_price", "", "₹", "amber");
    renderBarList("eda-dep-windows", eda.by_departure_window || [], "window", "mean_price");
    renderBarList("eda-months", eda.by_month || [], "label", "mean_price", "", "₹", "emerald");
    renderBarList("eda-weekdays", eda.by_weekday || [], "label", "mean_price");

    const limList = document.getElementById("market-limitations-list");
    limList.innerHTML = ((eda.market_limitations && eda.market_limitations.factors) || [])
      .map((txt) => `<li>${escapeHtml(txt)}</li>`)
      .join("");
  }

  // ---------------------- Watchlist & History CRUD ----------------------
  async function loadAlerts() {
    const tbody = document.getElementById("alerts-tbody");
    try {
      const res = await apiFetch("/api/alerts");
      if (!res.alerts.length) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted);">No fare alerts yet. Run an estimate and click "Save Route to Price Watchlist".</td></tr>';
        return;
      }
      tbody.innerHTML = res.alerts
        .map((a) => `
          <tr>
            <td class="font-mono">#${a.id}</td>
            <td>${escapeHtml(a.source_code)} → ${escapeHtml(a.dest_code)}</td>
            <td>${escapeHtml(a.airline)}</td>
            <td class="font-mono">${escapeHtml(a.journey_date)}</td>
            <td class="font-mono">₹${fmtInr(a.estimated_price)}</td>
            <td class="font-mono"><strong>₹${fmtInr(a.target_price)}</strong></td>
            <td><span class="badge ${a.status === "target_met" ? "badge-budget" : a.status === "paused" ? "badge-premium" : "badge-standard"}">${escapeHtml(a.status)}</span></td>
            <td>${escapeHtml(a.notes)}</td>
            <td style="white-space:nowrap;">
              <button type="button" class="btn btn-secondary btn-sm btn-edit-alert" data-id="${a.id}" data-target="${a.target_price}">Edit Target</button>
              <button type="button" class="btn btn-danger btn-sm btn-del-alert" data-id="${a.id}">Delete</button>
            </td>
          </tr>`)
        .join("");

      tbody.querySelectorAll(".btn-edit-alert").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const val = window.prompt("New Target Price (INR):", btn.dataset.target);
          if (!val) return;
          try {
            await apiFetch(`/api/alerts/${btn.dataset.id}`, {
              method: "PATCH",
              body: JSON.stringify({ target_price: parseFloat(val) }),
            });
            showToast("Alert updated.");
            loadAlerts();
          } catch (err) {
            showToast(err.message, true);
          }
        });
      });

      tbody.querySelectorAll(".btn-del-alert").forEach((btn) => {
        btn.addEventListener("click", async () => {
          try {
            await apiFetch(`/api/alerts/${btn.dataset.id}`, { method: "DELETE" });
            showToast("Alert deleted.");
            loadAlerts();
          } catch (err) {
            showToast(err.message, true);
          }
        });
      });
    } catch (err) {
      showToast(err.message, true);
    }
  }

  async function loadHistory() {
    const params = new URLSearchParams({ limit: "30" });
    const search = document.getElementById("history-search").value.trim();
    const airline = document.getElementById("history-airline-filter").value;
    if (search) params.set("search", search);
    if (airline) params.set("airline", airline);

    const res = await apiFetch(`/api/history?${params.toString()}`);
    const tbody = document.getElementById("history-tbody");
    if (!res.history.length) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);">No matching prediction records found.</td></tr>';
      return;
    }
    tbody.innerHTML = res.history
      .map((r) => `
        <tr>
          <td class="font-mono">#${r.id}</td>
          <td class="font-mono">${escapeHtml(r.timestamp)}</td>
          <td>${escapeHtml(r.airline)}</td>
          <td>${escapeHtml(r.route_str)}</td>
          <td>${escapeHtml(r.journey_date)} (${r.total_stops} stop)</td>
          <td class="font-mono"><strong>₹${fmtInr(r.predicted_fare)}</strong></td>
          <td>${escapeHtml(r.notes || "—")}</td>
          <td style="white-space:nowrap;">
            <button type="button" class="btn btn-secondary btn-sm btn-edit-pred" data-id="${r.id}" data-notes="${escapeHtml(r.notes)}">Edit Note</button>
            <button type="button" class="btn btn-danger btn-sm btn-del-pred" data-id="${r.id}">Delete</button>
          </td>
        </tr>`)
      .join("");

    tbody.querySelectorAll(".btn-edit-pred").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const nextNote = window.prompt("Update trip note:", btn.dataset.notes || "");
        if (nextNote === null) return;
        try {
          await apiFetch(`/api/history/${btn.dataset.id}`, {
            method: "PATCH",
            body: JSON.stringify({ notes: nextNote }),
          });
          showToast("Prediction note updated.");
          loadHistory();
        } catch (err) {
          showToast(err.message, true);
        }
      });
    });

    tbody.querySelectorAll(".btn-del-pred").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await apiFetch(`/api/history/${btn.dataset.id}`, { method: "DELETE" });
          showToast("Prediction record deleted.");
          loadHistory();
        } catch (err) {
          showToast(err.message, true);
        }
      });
    });
  }

  document.getElementById("btn-refresh-alerts").addEventListener("click", loadAlerts);
  document.getElementById("btn-refresh-history").addEventListener("click", loadHistory);
  document.getElementById("btn-filter-history").addEventListener("click", loadHistory);

  document.getElementById("btn-export-csv").addEventListener("click", async () => {
    try {
      const resp = await fetch("/api/history/export");
      if (!resp.ok) throw new Error("Unable to export CSV.");
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "farelens_predictions.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      showToast(err.message, true);
    }
  });

  // ---------------------- Database & Master Catalog ----------------------
  async function loadDbStudio() {
    const [dbRes, catRes] = await Promise.all([apiFetch("/api/db-status"), apiFetch("/api/catalog")]);
    document.getElementById("db-engine-badge").textContent = dbRes.db_type;
    document.getElementById("header-db-badge").textContent = `${dbRes.db_type} • Real-Time Airfare Intelligence`;

    const c = dbRes.table_counts || {};
    document.getElementById("db-kpi-grid").innerHTML = `
      <div class="kpi-card"><div class="label">Predictions Logged</div><div class="value">${c.flight_predictions || 0}</div><div class="sub">Saved searches</div></div>
      <div class="kpi-card"><div class="label">Watchlist Alerts</div><div class="value">${c.fare_alerts || 0}</div><div class="sub">Active price alerts</div></div>
      <div class="kpi-card"><div class="label">Master Airports</div><div class="value">${c.airports_master || 0}</div><div class="sub">Indexed domestic hubs</div></div>
      <div class="kpi-card"><div class="label">Master Airlines</div><div class="value">${c.airlines_master || 0}</div><div class="sub">Supported carriers</div></div>
    `;

    const airports = (catRes.master && catRes.master.airports) || [];
    document.getElementById("airports-preview").innerHTML = `
      <table class="data-table">
        <thead><tr><th>IATA</th><th>City</th><th>State / Region</th></tr></thead>
        <tbody>${airports
          .map((ap) => `<tr><td class="font-mono"><strong>${escapeHtml(ap.airport_code)}</strong></td><td>${escapeHtml(ap.city_name)}</td><td>${escapeHtml(ap.state_name)}</td></tr>`)
          .join("")}</tbody>
      </table>`;

    const airlines = (catRes.master && catRes.master.airlines) || [];
    document.getElementById("catalog-preview").innerHTML = `
      <table class="data-table">
        <thead><tr><th>Code</th><th>Airline Name</th><th>Tier</th></tr></thead>
        <tbody>${airlines
          .map((a) => `<tr><td class="font-mono">${escapeHtml(a.carrier_code)}</td><td>${escapeHtml(a.airline_name)}</td><td>${escapeHtml(a.airline_tier)}</td></tr>`)
          .join("")}</tbody>
      </table>`;
  }

  // ---------------------- Initialization ----------------------
  async function init() {
    try {
      const catRes = await apiFetch("/api/catalog");
      catalogData = catRes.catalog || {};

      const airlines = catalogData.airlines || ["IndiGo", "Air India", "Jet Airways", "SpiceJet"];
      airlineEl.innerHTML = airlines
        .map((a) => `<option value="${escapeHtml(a)}" ${a === "IndiGo" ? "selected" : ""}>${escapeHtml(a)}</option>`)
        .join("");

      const filterEl = document.getElementById("history-airline-filter");
      airlines.forEach((a) => {
        const opt = document.createElement("option");
        opt.value = a;
        opt.textContent = a;
        filterEl.appendChild(opt);
      });

      const infoOpts = catalogData.additional_info_options || ["No info"];
      infoEl.innerHTML = infoOpts
        .map((i) => `<option value="${escapeHtml(i)}" ${i === "No info" ? "selected" : ""}>${escapeHtml(i)}</option>`)
        .join("");

      updateRouteVisualizer();
      updateDuration();

      await Promise.all([loadAnalytics(), loadDbStudio(), runPredictionAndComparisons()]);
    } catch (err) {
      showToast(`Startup error: ${err.message}`, true);
    }
  }

  init();
});
