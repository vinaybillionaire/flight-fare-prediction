/**
 * AeroPrice - Real-Time Flight Fare Estimation Client Logic
 * Handles dynamic route visualizer, transit hub resolution, duration calculation,
 * and state transition from Empty Placeholder to Active Fare Estimate.
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const fareForm = document.getElementById("fare-form");
  const sourceSelect = document.getElementById("source");
  const destinationSelect = document.getElementById("destination");
  const airlineSelect = document.getElementById("airline");
  const stopsSelect = document.getElementById("total_stops");
  const journeyDateInput = document.getElementById("journey_date");
  const depTimeInput = document.getElementById("dep_time");
  const arrivalTimeInput = document.getElementById("arrival_time");
  const btnSubmit = document.getElementById("btn-submit");

  // Route & Duration Indicators
  const originPreview = document.querySelector(".origin-preview");
  const destPreview = document.querySelector(".dest-preview");
  const originName = document.querySelector(".origin-name");
  const destName = document.querySelector(".dest-name");
  const durationStripBox = document.getElementById("duration-strip-box");
  const durationPreviewText = document.getElementById("duration-preview-text");
  const transitHubsIndicator = document.getElementById("transit-hubs-indicator");
  const transitPathText = document.getElementById("transit-path-text");

  // Output State Containers
  const emptyStateView = document.getElementById("empty-state-view");
  const resultStateView = document.getElementById("result-state-view");

  // Result Elements
  const priceDisplay = document.getElementById("price-display");
  const priceRangeDisplay = document.getElementById("price-range-display");
  const fareTierBadge = document.getElementById("fare-tier-badge");
  const priceCaptionText = document.getElementById("price-caption-text");
  const summaryAirline = document.getElementById("summary-airline");
  const summaryRoute = document.getElementById("summary-route");
  const summaryTransitRow = document.getElementById("summary-transit-row");
  const summaryTransitStops = document.getElementById("summary-transit-stops");
  const summaryDuration = document.getElementById("summary-duration");
  const summaryStops = document.getElementById("summary-stops");
  const decompListContainer = document.getElementById("decomp-list-container");
  const savingsListContainer = document.getElementById("savings-list-container");

  // Airport Metadata Map
  const airportMeta = {
    "Banglore": { code: "BLR", name: "Bangalore" },
    "Delhi": { code: "DEL", name: "Delhi" },
    "New Delhi": { code: "DEL", name: "Delhi" },
    "Kolkata": { code: "CCU", name: "Kolkata" },
    "Chennai": { code: "MAA", name: "Chennai" },
    "Mumbai": { code: "BOM", name: "Mumbai" },
    "Cochin": { code: "COK", name: "Cochin" },
    "Hyderabad": { code: "HYD", name: "Hyderabad" }
  };

  // Intermediate Transit Hub Matrix for Indian Domestic Flights (Supports 1, 2, and 3 stops)
  const hubMatrix = {
    "Delhi_Cochin": ["Mumbai (BOM)", "Jaipur (JAI)", "Goa (GOI)"],
    "Kolkata_Banglore": ["Bhubaneswar (BBI)", "Ranchi (IXR)", "Hyderabad (HYD)"],
    "Banglore_Delhi": ["Mumbai (BOM)", "Ahmedabad (AMD)", "Jaipur (JAI)"],
    "Mumbai_Hyderabad": ["Delhi (DEL)", "Chennai (MAA)", "Pune (PNQ)"],
    "Chennai_Kolkata": ["Hyderabad (HYD)", "Bhubaneswar (BBI)", "Visakhapatnam (VTZ)"],
    "Chennai_Banglore": ["Hyderabad (HYD)", "Coimbatore (CJB)", "Tirupati (TIR)"],
    "Chennai_Hyderabad": ["Bangalore (BLR)", "Tirupati (TIR)", "Vijayawada (VGA)"],
    "Chennai_Delhi": ["Hyderabad (HYD)", "Nagpur (NAG)", "Bhopal (BHO)"],
    "Chennai_Cochin": ["Bangalore (BLR)", "Coimbatore (CJB)", "Madurai (IXM)"],
    "Mumbai_Banglore": ["Goa (GOI)", "Hyderabad (HYD)", "Pune (PNQ)"],
    "Mumbai_Delhi": ["Ahmedabad (AMD)", "Jaipur (JAI)", "Udaipur (UDR)"],
    "Mumbai_Cochin": ["Goa (GOI)", "Mangalore (IXE)", "Calicut (CCJ)"],
    "Mumbai_Kolkata": ["Nagpur (NAG)", "Bhubaneswar (BBI)", "Raipur (RPR)"],
    "Kolkata_Cochin": ["Chennai (MAA)", "Bangalore (BLR)", "Coimbatore (CJB)"],
    "Delhi_Hyderabad": ["Bhopal (BHO)", "Nagpur (NAG)", "Indore (IDR)"],
    "Delhi_Kolkata": ["Lucknow (LKO)", "Patna (PAT)", "Varanasi (VNS)"],
    "Banglore_Cochin": ["Coimbatore (CJB)", "Madurai (IXM)", "Calicut (CCJ)"],
    "Banglore_Hyderabad": ["Chennai (MAA)", "Tirupati (TIR)", "Vijayawada (VGA)"],
    "Banglore_Kolkata": ["Hyderabad (HYD)", "Bhubaneswar (BBI)", "Visakhapatnam (VTZ)"],
    "Delhi_Banglore": ["Mumbai (BOM)", "Hyderabad (HYD)", "Ahmedabad (AMD)"],
    "Kolkata_Delhi": ["Patna (PAT)", "Lucknow (LKO)", "Varanasi (VNS)"],
    "Kolkata_Hyderabad": ["Bhubaneswar (BBI)", "Raipur (RPR)", "Visakhapatnam (VTZ)"]
  };

  // Domestic Indian Air Corridor Standard Flight Times (in minutes)
  const corridorAirborneMinutes = {
    "Banglore_Hyderabad": 75,
    "Hyderabad_Banglore": 75,
    "Banglore_Delhi": 165,
    "Delhi_Banglore": 165,
    "Delhi_Cochin": 195,
    "Cochin_Delhi": 195,
    "Kolkata_Banglore": 155,
    "Banglore_Kolkata": 155,
    "Mumbai_Hyderabad": 85,
    "Hyderabad_Mumbai": 85,
    "Delhi_Kolkata": 135,
    "Kolkata_Delhi": 135,
    "Chennai_Kolkata": 140,
    "Kolkata_Chennai": 140,
    "Chennai_Banglore": 50,
    "Banglore_Chennai": 50,
    "Chennai_Hyderabad": 70,
    "Hyderabad_Chennai": 70,
    "Chennai_Delhi": 160,
    "Delhi_Chennai": 160,
    "Chennai_Cochin": 75,
    "Cochin_Chennai": 75,
    "Mumbai_Banglore": 95,
    "Banglore_Mumbai": 95,
    "Mumbai_Delhi": 130,
    "Delhi_Mumbai": 130,
    "Mumbai_Cochin": 110,
    "Cochin_Mumbai": 110,
    "Mumbai_Kolkata": 155,
    "Kolkata_Mumbai": 155,
    "Delhi_Hyderabad": 125,
    "Hyderabad_Delhi": 125,
    "Banglore_Cochin": 65,
    "Cochin_Banglore": 65,
    "Kolkata_Hyderabad": 125,
    "Hyderabad_Kolkata": 125,
    "Kolkata_Cochin": 195,
    "Cochin_Kolkata": 195
  };

  function getTransitHubs(src, dst, stops) {
    if (!src || !dst || stops <= 0) return [];
    const key = `${src}_${dst}`;
    const hubs = hubMatrix[key] || ["Mumbai (BOM)", "Delhi (DEL)"];
    return hubs.slice(0, stops);
  }

  function getAirborneMinutes(src, dst) {
    if (!src || !dst) return 130;
    const key = `${src}_${dst}`;
    return corridorAirborneMinutes[key] || 130;
  }

  // Auto-Calculate Realistic Arrival Time based on Route, Timing & Transit Layovers
  function autoCalculateArrival() {
    const dep = depTimeInput.value;
    if (!dep) return;

    const src = sourceSelect.value;
    const dst = destinationSelect.value;
    const stops = parseInt(stopsSelect.value || "0", 10);

    const airborneMins = getAirborneMinutes(src, dst);

    // Realistic domestic transit layover ground time
    let layoverMins = 0;
    if (stops === 1) {
      layoverMins = 210; // ~3h 30m standard transit layover
    } else if (stops === 2) {
      layoverMins = 420; // ~7h 00m combined layover across 2 transit airports
    } else if (stops >= 3) {
      layoverMins = 600; // ~10h 00m extended layover
    }

    const totalMins = airborneMins + layoverMins;

    const [depH, depM] = dep.split(":").map(Number);
    const totalDepMins = depH * 60 + depM;
    const totalArrMins = (totalDepMins + totalMins) % (24 * 60);

    const arrH = Math.floor(totalArrMins / 60);
    const arrM = totalArrMins % 60;

    arrivalTimeInput.value = `${String(arrH).padStart(2, "0")}:${String(arrM).padStart(2, "0")}`;

    updateDurationDisplay(totalMins, airborneMins, layoverMins, stops);
  }

  function updateDurationDisplay(totalMins, airborneMins, layoverMins, stops) {
    const hours = Math.floor(totalMins / 60);
    const mins = totalMins % 60;
    durationPreviewText.textContent = `${hours}h ${mins}m`;

    const stripBreakdown = document.getElementById("duration-strip-breakdown");
    if (stripBreakdown) {
      const airH = Math.floor(airborneMins / 60);
      const airM = airborneMins % 60;
      const airStr = airH > 0 ? `${airH}h ${airM}m` : `${airM}m`;

      if (stops === 0) {
        stripBreakdown.innerHTML = `<span><strong>Direct Non-stop:</strong> ~${airStr} airborne flying time</span>`;
      } else {
        const layH = Math.floor(layoverMins / 60);
        const layM = layoverMins % 60;
        const layStr = layM > 0 ? `${layH}h ${layM}m` : `${layH}h`;
        stripBreakdown.innerHTML = `<span><strong>Itinerary Breakdown:</strong> ~${airStr} flying + ~${layStr} transit layover at intermediate hub(s)</span>`;
      }
    }

    if (durationStripBox) durationStripBox.style.display = "flex";
  }

  // Handle Manual Arrival Time Input with Sanity Guardrails
  function onManualArrivalChange() {
    const dep = depTimeInput.value;
    const arr = arrivalTimeInput.value;
    if (!dep || !arr) return;

    const [depH, depM] = dep.split(":").map(Number);
    const [arrH, arrM] = arr.split(":").map(Number);

    let diff = (arrH * 60 + arrM) - (depH * 60 + depM);
    if (diff <= 0) diff += 24 * 60; // Overnight flight

    const stops = parseInt(stopsSelect.value || "0", 10);
    const src = sourceSelect.value;
    const dst = destinationSelect.value;
    const airborneMins = getAirborneMinutes(src, dst);

    const minThresholds = { 0: 45, 1: 180, 2: 360, 3: 540 };
    const minRequired = minThresholds[stops] || 45;

    if (diff < minRequired) {
      const hours = Math.floor(diff / 60);
      const mins = diff % 60;
      durationPreviewText.textContent = `${hours}h ${mins}m (Unrealistic)`;
      const stripBreakdown = document.getElementById("duration-strip-breakdown");
      if (stripBreakdown) {
        stripBreakdown.innerHTML = `
          <span style="color: var(--color-surge); font-weight: 600;">
            ⚠️ h m is too short for a -stop journey.
            <button type="button" class="btn-autofix" id="btn-autofix-time">Auto-Fix Schedule</button>
          </span>
        `;
        const autoFixBtn = document.getElementById("btn-autofix-time");
        if (autoFixBtn) {
          autoFixBtn.addEventListener("click", () => autoCalculateArrival());
        }
      }
      if (durationStripBox) durationStripBox.style.display = "flex";
    } else {
      const layoverMins = Math.max(0, diff - airborneMins);
      updateDurationDisplay(diff, airborneMins, layoverMins, stops);
    }
  }

  // Update Route Visualizer and Transit Hubs
  function updateRoute() {
    const src = sourceSelect.value;
    const dst = destinationSelect.value;
    const stops = parseInt(stopsSelect.value || "0", 10);

    if (src && airportMeta[src]) {
      originPreview.textContent = airportMeta[src].code;
      originName.textContent = airportMeta[src].name;
    } else {
      originPreview.textContent = "---";
      originName.textContent = "Origin";
    }

    if (dst && airportMeta[dst]) {
      destPreview.textContent = airportMeta[dst].code;
      destName.textContent = airportMeta[dst].name;
    } else {
      destPreview.textContent = "---";
      destName.textContent = "Destination";
    }

    // Display intermediate transit airports live if 1 or 2 stops are chosen
    if (src && dst && stops > 0) {
      const hubs = getTransitHubs(src, dst, stops);
      if (hubs.length > 0 && transitHubsIndicator && transitPathText) {
        transitPathText.textContent = hubs.join(" \u2794 ");
        transitHubsIndicator.style.display = "flex";
      }
    } else if (transitHubsIndicator) {
      transitHubsIndicator.style.display = "none";
    }

    // Auto-calculate realistic arrival whenever route or stops change
    autoCalculateArrival();
  }

  // Quick Flight Schedule Slot Chips
  const slotChips = document.querySelectorAll(".slot-chip");
  slotChips.forEach(chip => {
    chip.addEventListener("click", () => {
      slotChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      depTimeInput.value = chip.dataset.time;
      autoCalculateArrival();
    });
  });

  // Set default departure date to 7 days in future, min date to today
  if (journeyDateInput) {
    const today = new Date();
    const futureDate = new Date();
    futureDate.setDate(today.getDate() + 7);

    const pad = (n) => String(n).padStart(2, "0");
    journeyDateInput.min = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
    if (!journeyDateInput.value) {
      journeyDateInput.value = `${futureDate.getFullYear()}-${pad(futureDate.getMonth() + 1)}-${pad(futureDate.getDate())}`;
    }
  }

  // Prevent selecting identical Origin & Destination by dynamically disabling current selection
  function syncCityDropdowns() {
    const srcVal = sourceSelect.value;
    const dstVal = destinationSelect.value;

    Array.from(destinationSelect.options).forEach(opt => {
      if (opt.value && opt.value === srcVal) {
        opt.disabled = true;
      } else {
        opt.disabled = false;
      }
    });

    Array.from(sourceSelect.options).forEach(opt => {
      if (opt.value && opt.value === dstVal) {
        opt.disabled = true;
      } else {
        opt.disabled = false;
      }
    });

    // If currently identical, auto-select a valid alternative
    if (srcVal && dstVal && srcVal === dstVal) {
      const validDst = Array.from(destinationSelect.options).find(opt => opt.value && opt.value !== srcVal && !opt.disabled);
      if (validDst) {
        destinationSelect.value = validDst.value;
      }
    }
  }

  // Event Listeners for Live Form Changes
  sourceSelect.addEventListener("change", () => {
    syncCityDropdowns();
    updateRoute();
  });
  destinationSelect.addEventListener("change", () => {
    syncCityDropdowns();
    updateRoute();
  });
  stopsSelect.addEventListener("change", updateRoute);
  depTimeInput.addEventListener("input", autoCalculateArrival);
  arrivalTimeInput.addEventListener("input", onManualArrivalChange);

  // Initial Sync
  updateRoute();
  autoCalculateArrival();

  function getCategoryBadgeClass(category) {
    switch (category) {
      case "Budget": return "badge-budget";
      case "Standard": return "badge-standard";
      case "Premium": return "badge-premium";
      case "Surge": return "badge-surge";
      default: return "badge-standard";
    }
  }

  // Form Submit Action
  fareForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    if (!sourceSelect.value || !destinationSelect.value || !airlineSelect.value || stopsSelect.value === "") {
      alert("Please complete all flight selection fields.");
      return;
    }

    if (sourceSelect.value === destinationSelect.value) {
      alert("Origin and destination cities cannot be identical. Please select different airports.");
      return;
    }

    const payload = {
      airline: airlineSelect.value,
      source: sourceSelect.value,
      destination: destinationSelect.value,
      journey_date: journeyDateInput.value,
      dep_time: depTimeInput.value,
      arrival_time: arrivalTimeInput.value,
      total_stops: parseInt(stopsSelect.value, 10)
    };

    const originalText = btnSubmit.querySelector(".btn-text").textContent;
    btnSubmit.querySelector(".btn-text").textContent = "Calculating Fare...";
    btnSubmit.disabled = true;

    try {
      const response = await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Unable to estimate fare.");
      }

      const result = await response.json();

      // Transition from Empty State to Active Result
      if (emptyStateView) emptyStateView.style.display = "none";
      if (resultStateView) resultStateView.style.display = "block";

      // Update Price Display
      const fareInt = Math.floor(result.predicted_fare);
      priceDisplay.textContent = fareInt.toLocaleString("en-IN");

      fareTierBadge.textContent = `${result.fare_category} Fare`;
      fareTierBadge.className = `badge ${getCategoryBadgeClass(result.fare_category)}`;

      priceCaptionText.textContent = `Expected single passenger fare for ${result.flight_details.airline} (${result.flight_details.stops})`;

      // Update Breakdown Summary
      summaryAirline.textContent = result.flight_details.airline;
      summaryRoute.textContent = result.flight_details.route;
      summaryDuration.textContent = result.flight_details.duration;
      summaryStops.textContent = result.flight_details.stops;

      // Show intermediate transit hubs if stops > 0
      if (result.flight_details.transit_hubs && result.flight_details.transit_hubs.length > 0) {
        summaryTransitStops.textContent = result.flight_details.transit_hubs.join(" \u2022 ");
        summaryTransitRow.style.display = "flex";
      } else {
        summaryTransitRow.style.display = "none";
      }

      // Update Market Price Range
      if (priceRangeDisplay && result.fare_range) {
        priceRangeDisplay.textContent = `${result.fare_range.low} \u2014 ${result.fare_range.high}`;
      }

      // Render Transparent XAI Fare Decomposition
      if (decompListContainer && result.fare_decomposition) {
        decompListContainer.innerHTML = result.fare_decomposition.map(item => {
          let extraClass = "";
          if (item.amount.startsWith("-")) extraClass = "negative";
          else if (item.amount.startsWith("+")) extraClass = "positive";
          return `
            <div class="decomp-row">
              <span class="decomp-factor">${item.factor}</span>
              <span class="decomp-amount ${extraClass}">${item.amount}</span>
            </div>
          `;
        }).join("");
      }

      // Render Smart Schedule Optimizer Insights
      if (savingsListContainer && result.savings_insights) {
        savingsListContainer.innerHTML = result.savings_insights.map(tip => `
          <li class="savings-item">${tip}</li>
        `).join("");
      }

    } catch (err) {
      alert(`Fare Estimation Error: ${err.message}`);
    } finally {
      btnSubmit.querySelector(".btn-text").textContent = originalText;
      btnSubmit.disabled = false;
    }
  });
});
