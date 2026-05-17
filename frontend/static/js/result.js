const gaugeNeedle = document.getElementById("gaugeNeedle");
const errorBox = document.getElementById("errorBox");

function updateGauge(score, color) {
  const pct = Math.max(0, Math.min(100, ((Number(score) - 1) / 9) * 100));
  gaugeNeedle.style.left = `${pct}%`;
  gaugeNeedle.style.background = color || "#2563eb";
}

function renderPrediction(data) {
  if (!data || !data.stress_score) {
    errorBox.textContent = "No result found. Please submit the stress input form first.";
    return;
  }

  document.getElementById("scoreValue").textContent = Number(data.stress_score).toFixed(3);
  document.getElementById("labelValue").textContent = data.stress_label;
  document.getElementById("labelValue").style.color = data.color;
  document.getElementById("scoreBox").style.borderLeftColor = data.color;
  document.getElementById("tipValue").textContent = data.tip;
  document.getElementById("driverValue").textContent = data.tip_driver || "general";
  document.getElementById("savedValue").textContent = data.saved ? "Yes" : "No";
  document.getElementById("resultDateText").textContent = data.date ? `Result for ${data.date}` : "Review your saved daily prediction.";
  updateGauge(data.stress_score, data.color);

  const emailValue = document.getElementById("emailValue");
  if (data.stress_label === "High") {
    emailValue.textContent = data.email_sent ? "High alert sent" : `Not sent: ${data.email_message || "email not configured"}`;
    emailValue.className = data.email_sent ? "ok-text" : "warn-text";
  } else {
    emailValue.textContent = "Not needed for this label";
    emailValue.className = "";
  }
}

const stored = sessionStorage.getItem("latestPrediction");
renderPrediction(stored ? JSON.parse(stored) : null);