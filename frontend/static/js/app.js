const form = document.getElementById("stressForm");
const dateInput = document.getElementById("dateInput");
const weekdayInput = document.getElementById("weekdayInput");
const weekdayDisplay = document.getElementById("weekdayDisplay");
const datePretty = document.getElementById("datePretty");
const submitBtn = document.getElementById("submitBtn");
const submissionBanner = document.getElementById("submissionBanner");
const toast = document.getElementById("toast");
const weekdayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function showToast(message, type = "info") {
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  window.setTimeout(() => {
    toast.className = "toast";
  }, 3200);
}

function weekdayFromDate(dateValue) {
  const date = new Date(`${dateValue}T00:00:00`);
  return date.getDay() === 0 ? 6 : date.getDay() - 1;
}

function formatPrettyDate(dateValue) {
  const date = new Date(`${dateValue}T00:00:00`);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function updateWeekdayFromDate() {
  const weekday = weekdayFromDate(dateInput.value);
  weekdayInput.value = String(weekday);
  weekdayDisplay.textContent = weekdayNames[weekday];
  datePretty.textContent = formatPrettyDate(dateInput.value);
}

function setupNumberInputs() {
  document.querySelectorAll(".metric-field input[type='number']").forEach((input) => {
    input.addEventListener("blur", () => {
      const min = Number(input.min);
      const max = Number(input.max);
      const value = Number(input.value);
      if (Number.isNaN(value)) return;
      input.value = String(Math.min(max, Math.max(min, value)));
    });
  });
}

function setBanner(submitted, record) {
  submissionBanner.className = submitted ? "submission-banner locked" : "submission-banner";
  if (submitted) {
    submissionBanner.innerHTML = `
      <strong>Already submitted for ${formatPrettyDate(dateInput.value)}</strong>
      <span>${record?.stress_label || "Saved"} check-in found. You can view it on the dashboard.</span>
    `;
    submitBtn.disabled = true;
    submitBtn.textContent = "Already Submitted Today";
  } else {
    submissionBanner.innerHTML = `
      <strong>Ready for ${formatPrettyDate(dateInput.value)}</strong>
      <span>You can submit one private check-in for this date.</span>
    `;
    submitBtn.disabled = false;
    submitBtn.textContent = "Predict Stress";
  }
}

async function checkSubmissionStatus() {
  updateWeekdayFromDate();
  try {
    const response = await fetch(`/api/submission-status?date=${encodeURIComponent(dateInput.value)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not check submission status");
    setBanner(data.submitted, data.record);
  } catch (error) {
    submissionBanner.className = "submission-banner warning";
    submissionBanner.innerHTML = `<strong>Status unavailable</strong><span>${error.message}</span>`;
  }
}

function formToPayload() {
  updateWeekdayFromDate();
  const payload = {};
  new FormData(form).forEach((value, key) => {
    payload[key] = key === "date" ? value : Number(value);
  });
  return payload;
}

function openResultPage(data) {
  sessionStorage.setItem("latestPrediction", JSON.stringify(data));
  window.location.href = "/result";
}

function existingToResult(data) {
  const labelColors = { Low: "#27AE60", Moderate: "#E67E22", High: "#C0392B" };
  return {
    stress_score: data.stress_score,
    stress_label: data.stress_label,
    color: labelColors[data.stress_label] || "#2563eb",
    tip: data.tip || "This check-in is already saved.",
    tip_driver: data.tip_driver || "saved_record",
    saved: true,
    email_sent: false,
    email_message: "Already saved record",
    date: data.date,
    already_submitted: true,
  };
}

const today = new Date();
const todayValue = today.toISOString().slice(0, 10);
dateInput.value = todayValue;
dateInput.max = todayValue;
updateWeekdayFromDate();
setupNumberInputs();
checkSubmissionStatus();

dateInput.addEventListener("change", checkSubmissionStatus);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (submitBtn.disabled) return;

  submitBtn.disabled = true;
  submitBtn.textContent = "Predicting...";
  document.getElementById("errorBox").textContent = "";

  try {
    const response = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formToPayload()),
    });

    const data = await response.json();
    if (!response.ok) {
      if (response.status === 409 && data.already_submitted) {
        setBanner(true, data);
        openResultPage(existingToResult(data));
        return;
      }
      throw new Error(data.error || "Prediction failed");
    }

    setBanner(true, data);
    openResultPage(data);
  } catch (error) {
    document.getElementById("errorBox").textContent = error.message;
    showToast(error.message, "warn");
    submitBtn.disabled = false;
    submitBtn.textContent = "Predict Stress";
  }
});
