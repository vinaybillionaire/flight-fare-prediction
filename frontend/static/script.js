/**
 * FareLens — Interactive Multi-Role Airfare Intelligence Client
 */
document.addEventListener("DOMContentLoaded", () => {
  const TOKEN_KEY = "farelens_jwt_token";
  const USER_KEY = "farelens_user_obj";

  let authToken = localStorage.getItem(TOKEN_KEY) || null;
  let currentUser = null;
  try {
    currentUser = JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    currentUser = null;
  }

  let catalogData = null;
  let lastPredictionResult = null;
  let lastPayload = null;

  // DOM References
  const toastEl = document.getElementById("toast");
  const rolePill = document.getElementById("user-role-pill");
  const btnOpenAuth = document.getElementById("btn-open-auth");
  const btnSignout = document.getElementById("btn-signout");
  const authModal = document.getElementById("auth-modal");
  const vivaModal = document.getElementById("viva-modal");

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
    if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
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

  // ---------------------- Auth State & Modals ----------------------
  function syncAuthUI() {
    const exportBtn = document.getElementById("btn-export-csv");
    if (currentUser && authToken) {
      rolePill.textContent = `${currentUser.full_name} (${currentUser.role.toUpperCase()})`;
      rolePill.className = currentUser.role === "admin" ? "badge badge-admin" : "badge badge-budget";
      btnOpenAuth.textContent = "Switch Account";
      btnSignout.style.display = "inline-flex";
      btnSaveAlert.disabled = !lastPredictionResult;
      btnSaveAlert.textContent = "Save Route to Price Watchlist";
      exportBtn.style.display = ["analyst", "admin"].includes(currentUser.role)
        ? "inline-flex"
        : "none";
    } else {
      rolePill.textContent = "Guest Mode";
      rolePill.className = "badge badge-subtle";
      btnOpenAuth.textContent = "Sign In / Register";
      btnSignout.style.display = "none";
      btnSaveAlert.disabled = !lastPredictionResult;
      btnSaveAlert.textContent = "Save to Price Watchlist (Sign In Required)";
      exportBtn.style.display = "none";
    }
  }

  function setSession(token, user) {
    authToken = token;
    currentUser = user;
    if (token && user) {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
    syncAuthUI();
  }

  function openModal(modal) {
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeModal(modal) {
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  }

  btnOpenAuth.addEventListener("click", () => openModal(authModal));
  document.getElementById("btn-close-auth").addEventListener("click", () => closeModal(authModal));
  document.getElementById("btn-open-viva").addEventListener("click", () => openModal(vivaModal));
  document.getElementById("btn-close-viva").addEventListener("click", () => closeModal(vivaModal));

  [authModal, vivaModal].forEach((m) => {
    m.addEventListener("click", (e) => {
      if (e.target === m) closeModal(m);
    });
  });

  btnSignout.addEventListener("click", () => {
    setSession(null, null);
    showToast("Signed out.");
    loadAlerts();
    loadDbStudio();
  });

  document.querySelectorAll(".demo-login-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const res = await apiFetch("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({ email: btn.dataset.email, password: btn.dataset.pw }),
        });
        setSession(res.access_token, res.user);
        closeModal(authModal);
        showToast(`Signed in as ${res.user.full_name} (${res.user.role})`);
        loadAlerts();
        loadHistory();
        loadDbStudio();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  });

  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const res = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: document.getElementById("login-email").value,
          password: document.getElementById("login-password").value,
        }),
      });
      setSession(res.access_token, res.user);
      closeModal(authModal);
      showToast(`Welcome back, ${res.user.full_name}!`);
      loadAlerts();
      loadDbStudio();
    } catch (err) {
      showToast(err.message, true);
    }
  });

  document.getElementById("register-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const res = await apiFetch("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          full_name: document.getElementById("reg-name").value,
          email: document.getElementById("reg-email").value,
          password: document.getElementById("reg-password").value,
          role: document.getElementById("reg-role").value,
        }),
      });
      setSession(res.access_token, res.user);
      closeModal(authModal);
      showToast(`Registered & signed in as ${res.user.role}!`);
      loadAlerts();
    } catch (err) {
      showToast(err.message, true);
    }
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
      ? `${matches.length} historical layover paths found`
      : "Synthetic fallback path";
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
    btnSubmit.textContent = "Computing ML Inference & Batch Intelligence...";
    try {
      const [predRes, dateRes, airlineRes] = await Promise.all([
        apiFetch("/api/predict", { method: "POST", body: JSON.stringify(payload) }),
        apiFetch("/api/compare-dates", { method: "POST", body: JSON.stringify(payload) }),
        apiFetch("/api/compare-airlines", { method: "POST", body: JSON.stringify(payload) }),
      ]);

      lastPredictionResult = predRes;
      lastPayload = payload;
      renderPredictionCard(predRes);
      renderFlexDates(dateRes);
      renderAirlineComparisons(airlineRes);
      syncAuthUI();
    } catch (err) {
      showToast(err.message, true);
    } finally {
      btnSubmit.disabled = false;
      btnSubmit.textContent = "Estimate Fare & Run Intelligence";
    }
  }

  function renderPredictionCard(res) {
    document.getElementById("price-display").textContent = fmtInr(res.predicted_fare);
    document.getElementById("price-range-pill").textContent =
      `IQR Confidence Band: ₹${fmtInr(res.confidence_interval.lower)} – ₹${fmtInr(res.confidence_interval.upper)}`;
    const badge = document.getElementById("fare-tier-badge");
    badge.textContent = `${res.fare_category} Fare`;
    badge.className = `badge ${badgeClass(res.fare_category)}`;
    document.getElementById("price-caption-text").textContent =
      `${res.model_info.algorithm} • R² ${(res.model_info.r2_score * 100).toFixed(2)}% • Logged #${res.prediction_id}`;

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
    if (!authToken) {
      authModal.classList.add("open");
      showToast("Sign in first to save a Watchlist Alert.", true);
      return;
    }
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
          notes: lastPayload.notes || "Watched from Estimator",
        }),
      });
      showToast("Saved to Price Watchlist!");
      loadAlerts();
    } catch (err) {
      showToast(err.message, true);
    }
  });

  // ---------------------- EDA & Benchmarks Loaders ----------------------
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

  async function loadAnalyticsAndBenchmarks() {
    const [analyticsRes, metricsRes] = await Promise.all([
      apiFetch("/api/analytics"),
      apiFetch("/api/metrics"),
    ]);

    const eda = analyticsRes.eda || {};
    const ov = eda.dataset_overview || {};
    document.getElementById("eda-kpis").innerHTML = `
      <div class="kpi-card"><div class="label">Cleaned Records</div><div class="value">${fmtInr(ov.cleaned_records)}</div><div class="sub">${ov.duplicates_removed || 220} duplicates removed</div></div>
      <div class="kpi-card"><div class="label">Mean / Median Fare</div><div class="value">₹${fmtInr(ov.mean_price)}</div><div class="sub">Median: ₹${fmtInr(ov.median_price)}</div></div>
      <div class="kpi-card"><div class="label">Fare Range</div><div class="value">₹${fmtInr(ov.min_price)}</div><div class="sub">Max Business: ₹${fmtInr(ov.max_price)}</div></div>
      <div class="kpi-card"><div class="label">Error ≤ ₹1,000</div><div class="value">${ov.within_1000_inr_pct || 0}%</div><div class="sub">≤ ₹1,500: ${ov.within_1500_inr_pct || 0}%</div></div>
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

    // Benchmarks
    const metrics = metricsRes.metrics || {};
    const selectedName = metrics.selected_model || "Random Forest (Tuned Final)";
    const modelEntries = Object.entries(metrics.models || {});
    const selStats = (metrics.models && metrics.models[selectedName]) || {};

    if (selStats.r2_score) {
      document.getElementById("header-r2-badge").textContent = `R² ${(selStats.r2_score * 100).toFixed(2)}%`;
      document.getElementById("hero-r2").textContent = `${(selStats.r2_score * 100).toFixed(2)}%`;
      document.getElementById("hero-mae").textContent = `₹${fmtInr(selStats.mae)}`;
      if (selStats.cv_r2_mean) {
        document.getElementById("hero-cv").textContent = `${(selStats.cv_r2_mean * 100).toFixed(2)}%`;
      }
    }

    document.getElementById("benchmarks-tbody").innerHTML = modelEntries
      .map(([name, s]) => `
        <tr class="${s.is_selected ? "selected-row" : ""}">
          <td><strong>${escapeHtml(name)}</strong></td>
          <td class="font-mono">${(s.r2_score * 100).toFixed(2)}%</td>
          <td class="font-mono">₹${fmtInr(s.mae)}</td>
          <td class="font-mono">₹${fmtInr(s.rmse)}</td>
          <td class="font-mono">${s.mape_pct}%</td>
          <td>${s.is_selected ? '<span class="badge badge-budget">Deployed</span>' : '<span class="badge badge-subtle">Benchmarked</span>'}</td>
        </tr>`)
      .join("");

    const r2Items = modelEntries.map(([name, s]) => ({
      name,
      r2_pct: Number((s.r2_score * 100).toFixed(2)),
    }));
    renderBarList("benchmark-r2-bars", r2Items, "name", "r2_pct", "%", "", "emerald");
  }

  // ---------------------- Watchlist & History CRUD ----------------------
  async function loadAlerts() {
    const notice = document.getElementById("alerts-auth-notice");
    const tbody = document.getElementById("alerts-tbody");
    if (!authToken) {
      notice.style.display = "block";
      tbody.innerHTML = "";
      return;
    }
    notice.style.display = "none";
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
    const mine = document.getElementById("history-mine-only").checked;
    if (search) params.set("search", search);
    if (airline) params.set("airline", airline);
    if (mine) params.set("mine", "true");

    const res = await apiFetch(`/api/history?${params.toString()}`);
    const tbody = document.getElementById("history-tbody");
    if (!res.history.length) {
      tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted);">No matching prediction records found.</td></tr>';
      return;
    }
    tbody.innerHTML = res.history
      .map((r) => `
        <tr>
          <td class="font-mono">#${r.id}</td>
          <td class="font-mono">${escapeHtml(r.timestamp)}</td>
          <td>${escapeHtml(r.user_email)}</td>
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
        if (!authToken) {
          authModal.classList.add("open");
          showToast("Sign in to edit prediction notes.", true);
          return;
        }
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
        if (!authToken) {
          authModal.classList.add("open");
          showToast("Sign in to delete prediction logs.", true);
          return;
        }
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
      const resp = await fetch("/api/history/export", {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!resp.ok) throw new Error("Export requires Analyst or Admin role.");
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

  // ---------------------- Admin & DB Studio ----------------------
  async function loadDbStudio() {
    const [dbRes, catRes] = await Promise.all([apiFetch("/api/db-status"), apiFetch("/api/catalog")]);
    document.getElementById("db-engine-badge").textContent = dbRes.db_type;
    document.getElementById("header-db-badge").textContent = `${dbRes.db_type} • Group G1716`;

    const c = dbRes.table_counts || {};
    document.getElementById("db-kpi-grid").innerHTML = `
      <div class="kpi-card"><div class="label">Stakeholder Users</div><div class="value">${c.users || 0}</div><div class="sub">Traveler / Analyst / Admin</div></div>
      <div class="kpi-card"><div class="label">Predictions Logged</div><div class="value">${c.flight_predictions || 0}</div><div class="sub">FK-linked transaction rows</div></div>
      <div class="kpi-card"><div class="label">Watchlist Alerts</div><div class="value">${c.fare_alerts || 0}</div><div class="sub">CASCADE FK to users</div></div>
      <div class="kpi-card"><div class="label">Master Catalog</div><div class="value">${(c.airports_master || 0) + (c.airlines_master || 0)}</div><div class="sub">${c.airports_master || 0} Airports • ${c.airlines_master || 0} Airlines</div></div>
    `;

    const airlines = (catRes.master && catRes.master.airlines) || [];
    document.getElementById("catalog-preview").innerHTML = `
      <table class="data-table">
        <thead><tr><th>Code</th><th>Airline Name</th><th>Tier</th></tr></thead>
        <tbody>${airlines
          .map((a) => `<tr><td class="font-mono">${escapeHtml(a.carrier_code)}</td><td>${escapeHtml(a.airline_name)}</td><td>${escapeHtml(a.airline_tier)}</td></tr>`)
          .join("")}</tbody>
      </table>`;

    const usersWrap = document.getElementById("admin-users-wrap");
    if (!currentUser || currentUser.role !== "admin") {
      usersWrap.innerHTML = `<p class="card-desc">Sign in as <strong>Admin</strong> (<code>admin@farelens.in</code>) to view and manage stakeholder accounts.</p>`;
      return;
    }

    try {
      const usersRes = await apiFetch("/api/admin/users");
      usersWrap.innerHTML = `
        <div class="table-responsive">
          <table class="data-table">
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th></tr></thead>
            <tbody>${usersRes.users
              .map(
                (u) => `
                <tr>
                  <td>${escapeHtml(u.full_name)}</td>
                  <td class="font-mono">${escapeHtml(u.email)}</td>
                  <td>
                    <select class="admin-role-select" data-id="${u.id}">
                      <option value="traveler" ${u.role === "traveler" ? "selected" : ""}>traveler</option>
                      <option value="analyst" ${u.role === "analyst" ? "selected" : ""}>analyst</option>
                      <option value="admin" ${u.role === "admin" ? "selected" : ""}>admin</option>
                    </select>
                  </td>
                  <td><span class="badge ${u.is_active ? "badge-budget" : "badge-surge"}">${u.is_active ? "Active" : "Disabled"}</span></td>
                </tr>`
              )
              .join("")}</tbody>
          </table>
        </div>`;

      usersWrap.querySelectorAll(".admin-role-select").forEach((sel) => {
        sel.addEventListener("change", async () => {
          try {
            await apiFetch(`/api/admin/users/${sel.dataset.id}`, {
              method: "PATCH",
              body: JSON.stringify({ role: sel.value }),
            });
            showToast("User role updated.");
          } catch (err) {
            showToast(err.message, true);
          }
        });
      });
    } catch (err) {
      usersWrap.innerHTML = `<p class="card-desc">${escapeHtml(err.message)}</p>`;
    }
  }

  document.getElementById("admin-airline-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!currentUser || currentUser.role !== "admin") {
      authModal.classList.add("open");
      showToast("Admin role required to add airlines.", true);
      return;
    }
    try {
      await apiFetch("/api/admin/airlines", {
        method: "POST",
        body: JSON.stringify({
          airline_name: document.getElementById("new-airline-name").value,
          carrier_code: document.getElementById("new-carrier-code").value,
          airline_tier: document.getElementById("new-airline-tier").value,
        }),
      });
      showToast("Airline added to master table.");
      document.getElementById("admin-airline-form").reset();
      loadDbStudio();
    } catch (err) {
      showToast(err.message, true);
    }
  });

  // ---------------------- Initialization ----------------------
  async function init() {
    syncAuthUI();
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

      await Promise.all([loadAnalyticsAndBenchmarks(), loadDbStudio(), runPredictionAndComparisons()]);
    } catch (err) {
      showToast(`Startup error: ${err.message}`, true);
    }
  }

  init();
});
