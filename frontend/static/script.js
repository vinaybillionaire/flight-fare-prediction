/**
 * AeroPrice - Real-Time Flight Fare Estimation Client Logic
 * Powers live route updates, duration computation, and API estimation requests.
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
  const durationPreviewText = document.getElementById("duration-preview-text");

  // Output Card Elements
  const priceDisplay = document.getElementById("price-display");
  const fareTierBadge = document.getElementById("fare-tier-badge");
  const priceCaptionText = document.getElementById("price-caption-text");
  const summaryAirline = document.getElementById("summary-airline");
  const summaryRoute = document.getElementById("summary-route");
  const summaryDuration = document.getElementById("summary-duration");
  const summaryStops = document.getElementById("summary-stops");
  const summaryInsight = document.getElementById("summary-insight");

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

  // Set default journey date to tomorrow
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const yyyy = tomorrow.getFullYear();
  const mm = String(tomorrow.getMonth() + 1).padStart(2, "0");
  const dd = String(tomorrow.getDate()).padStart(2, "0");
  if (journeyDateInput && !journeyDateInput.value) {
    journeyDateInput.value = `${yyyy}-${mm}-${dd}`;
  }

  // Update Flight Duration Preview
  function updateDuration() {
    const dep = depTimeInput.value;
    const arr = arrivalTimeInput.value;
    if (!dep || !arr) return;

    const [depH, depM] = dep.split(":").map(Number);
    const [arrH, arrM] = arr.split(":").map(Number);

    let diff = (arrH * 60 + arrM) - (depH * 60 + depM);
    if (diff <= 0) {
      diff += 24 * 60; // Overnight flight
    }

    const hours = Math.floor(diff / 60);
    const mins = diff % 60;
    durationPreviewText.textContent = `${hours}h ${mins}m`;
  }

  // Update Route Visualizer
  function updateRoute() {
    const src = sourceSelect.value;
    const dst = destinationSelect.value;

    const srcData = airportMeta[src] || { code: src.substring(0, 3).toUpperCase(), name: src };
    const dstData = airportMeta[dst] || { code: dst.substring(0, 3).toUpperCase(), name: dst };

    originPreview.textContent = srcData.code;
    originName.textContent = srcData.name;
    destPreview.textContent = dstData.code;
    destName.textContent = dstData.name;
  }

  // Event Listeners for Live Form Changes
  sourceSelect.addEventListener("change", updateRoute);
  destinationSelect.addEventListener("change", updateRoute);
  depTimeInput.addEventListener("input", updateDuration);
  arrivalTimeInput.addEventListener("input", updateDuration);

  // Initial Sync
  updateRoute();
  updateDuration();

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

    if (sourceSelect.value === destinationSelect.value) {
      alert("Origin and destination cities cannot be identical. Please choose different airports.");
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

      // Booking Insight Badge
      if (result.fare_category === "Budget") {
        summaryInsight.innerHTML = "<span style='color: var(--color-budget); font-weight:700;'>Great Value &bull; Good time to book</span>";
      } else if (result.fare_category === "Standard") {
        summaryInsight.innerHTML = "<span style='color: var(--color-standard); font-weight:700;'>Fair Price &bull; Typical for route</span>";
      } else {
        summaryInsight.innerHTML = "<span style='color: var(--color-surge); font-weight:700;'>High Demand &bull; Peak booking window</span>";
      }

    } catch (err) {
      alert(`Fare Estimation Error: ${err.message}`);
    } finally {
      btnSubmit.querySelector(".btn-text").textContent = originalText;
      btnSubmit.disabled = false;
    }
  });
});
