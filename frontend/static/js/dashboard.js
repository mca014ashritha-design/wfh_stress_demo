const totalPredictions = document.getElementById("totalPredictions");
const averageScore = document.getElementById("averageScore");
const latestLabel = document.getElementById("latestLabel");
const latestDate = document.getElementById("latestDate");
const trendValue = document.getElementById("trendValue");
const trendDelta = document.getElementById("trendDelta");
const scoreChart = document.getElementById("scoreChart");
const distributionBox = document.getElementById("distributionBox");
const driverBox = document.getElementById("driverBox");
const recordsBody = document.getElementById("recordsBody");
const weeklyTrendTitle = document.getElementById("weeklyTrendTitle");
const weeklyTrendText = document.getElementById("weeklyTrendText");
const thisWeekAvg = document.getElementById("thisWeekAvg");
const lastWeekAvg = document.getElementById("lastWeekAvg");
const weeklyDelta = document.getElementById("weeklyDelta");
const weeklyTip = document.getElementById("weeklyTip");
const focusAreas = document.getElementById("focusAreas");
const weeklyBars = document.getElementById("weeklyBars");
const emailWeeklyBtn = document.getElementById("emailWeeklyBtn");
const weeklyEmailStatus = document.getElementById("weeklyEmailStatus");

const labelColors = {
  Low: "#27AE60",
  Moderate: "#E67E22",
  High: "#C0392B",
};

const trendCopy = {
  WORSENING: "Your stress average increased this week.",
  IMPROVING: "Your stress average improved this week.",
  STABLE: "Your stress average stayed steady this week.",
  NO_DATA: "Add predictions to generate a weekly report.",
};

function setText(node, value) {
  node.textContent = value;
}

function prettyDriver(driver) {
  return String(driver || "general").replaceAll("_", " ");
}

function renderEmpty() {
  scoreChart.innerHTML = '<div class="empty-state">No predictions yet. Add one from the prediction page.</div>';
  distributionBox.innerHTML = '<div class="empty-state">No label data yet.</div>';
  driverBox.innerHTML = '<div class="empty-state">No driver data yet.</div>';
  recordsBody.innerHTML = '<tr><td colspan="5">No records found.</td></tr>';
}

function renderScores(history) {
  if (!history.length) {
    scoreChart.innerHTML = '<div class="empty-state">No predictions yet. Add one from the prediction page.</div>';
    return;
  }

  scoreChart.innerHTML = history.map((item) => {
    const score = Number(item.stress_score || 0);
    const height = Math.max(8, Math.round(score * 10));
    const color = labelColors[item.stress_label] || "#2563eb";
    return `
      <div class="score-bar-item" title="${item.date}: ${score.toFixed(2)}">
        <div class="score-bar" style="height:${height}%; background:${color}"></div>
        <span>${score.toFixed(1)}</span>
      </div>
    `;
  }).join("");
}

function renderDistribution(distribution, total) {
  const labels = ["Low", "Moderate", "High"];
  distributionBox.innerHTML = labels.map((label) => {
    const count = distribution[label] || 0;
    const pct = total ? Math.round((count / total) * 100) : 0;
    return `
      <div class="dist-row">
        <div><b>${label}</b><span>${count} records</span></div>
        <div class="dist-track"><span style="width:${pct}%; background:${labelColors[label]}"></span></div>
        <strong>${pct}%</strong>
      </div>
    `;
  }).join("");
}

function renderDrivers(driverCounts) {
  const entries = Object.entries(driverCounts).sort((a, b) => b[1] - a[1]).slice(0, 5);
  if (!entries.length) {
    driverBox.innerHTML = '<div class="empty-state">No driver data yet.</div>';
    return;
  }

  const max = Math.max(...entries.map((entry) => entry[1]));
  driverBox.innerHTML = entries.map(([driver, count]) => {
    const width = Math.max(12, Math.round((count / max) * 100));
    return `
      <div class="driver-row">
        <div><b>${prettyDriver(driver)}</b><span>${count}</span></div>
        <div class="driver-track"><span style="width:${width}%"></span></div>
      </div>
    `;
  }).join("");
}

function renderWeekly(weekly) {
  const report = weekly || {};
  const trend = report.trend || "NO_DATA";
  const delta = Number(report.delta || 0);
  const days = report.days || [];

  setText(weeklyTrendTitle, trend.replaceAll("_", " "));
  setText(weeklyTrendText, trendCopy[trend] || trendCopy.STABLE);
  setText(thisWeekAvg, Number(report.this_week_avg || 0).toFixed(2));
  setText(lastWeekAvg, Number(report.last_week_avg || 0).toFixed(2));
  setText(weeklyDelta, `${delta >= 0 ? "+" : ""}${delta.toFixed(2)}`);
  setText(weeklyTip, report.weekly_tip || "Add predictions to generate your weekly tip.");

  focusAreas.innerHTML = (report.focus_areas || []).length
    ? report.focus_areas.map((driver) => `<span>${prettyDriver(driver)}</span>`).join("")
    : '<span>No focus area yet</span>';

  if (!days.length) {
    weeklyBars.innerHTML = '<div class="empty-state">No weekly data yet.</div>';
    return;
  }

  weeklyBars.innerHTML = days.map((item) => {
    const score = Number(item.stress_score || 0);
    const color = labelColors[item.stress_label] || "#2563eb";
    const height = Math.max(10, Math.round(score * 10));
    const dateLabel = String(item.date || "").slice(5) || "--";
    return `
      <div class="weekly-day" title="${item.date}: ${score.toFixed(2)}">
        <div class="weekly-day-bar" style="height:${height}%; background:${color}"></div>
        <strong>${score.toFixed(1)}</strong>
        <span>${dateLabel}</span>
      </div>
    `;
  }).join("");
}

function renderRecords(history) {
  if (!history.length) {
    recordsBody.innerHTML = '<tr><td colspan="5">No records found.</td></tr>';
    return;
  }

  recordsBody.innerHTML = [...history].reverse().map((item) => `
    <tr>
      <td>${item.date || "--"}</td>
      <td>${Number(item.stress_score || 0).toFixed(2)}</td>
      <td><span class="label-pill" style="background:${labelColors[item.stress_label] || "#2563eb"}">${item.stress_label || "--"}</span></td>
      <td>${prettyDriver(item.tip_driver)}</td>
      <td>${item.tip || "--"}</td>
    </tr>
  `).join("");
}

async function loadDashboard() {
  try {
    const response = await fetch("/api/dashboard");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Dashboard failed to load");
    }

    setText(totalPredictions, data.total);
    setText(averageScore, Number(data.average || 0).toFixed(2));

    if (data.latest) {
      setText(latestLabel, data.latest.stress_label);
      latestLabel.style.color = labelColors[data.latest.stress_label] || "#172033";
      setText(latestDate, data.latest.date);
    } else {
      setText(latestLabel, "--");
      setText(latestDate, "No prediction yet");
    }

    setText(trendValue, data.trend.replaceAll("_", " "));
    setText(trendDelta, `Delta ${Number(data.delta || 0).toFixed(2)} vs previous week`);
    renderWeekly(data.weekly);

    if (!data.total) {
      renderEmpty();
      return;
    }

    renderScores(data.history || []);
    renderDistribution(data.distribution || {}, data.total || 0);
    renderDrivers(data.driver_counts || {});
    renderRecords(data.history || []);
  } catch (error) {
    scoreChart.innerHTML = `<div class="empty-state error">${error.message}</div>`;
  }
}

if (emailWeeklyBtn) {
  emailWeeklyBtn.addEventListener("click", async () => {
    weeklyEmailStatus.textContent = "Sending weekly report...";
    weeklyEmailStatus.className = "email-status";
    emailWeeklyBtn.disabled = true;

    try {
      const response = await fetch("/api/email-weekly-report", { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Could not send weekly report");
      }
      weeklyEmailStatus.textContent = data.sent ? "Weekly report emailed successfully." : `Email not sent: ${data.message}`;
      weeklyEmailStatus.className = data.sent ? "email-status ok-text" : "email-status warn-text";
    } catch (error) {
      weeklyEmailStatus.textContent = error.message;
      weeklyEmailStatus.className = "email-status warn-text";
    } finally {
      emailWeeklyBtn.disabled = false;
    }
  });
}

loadDashboard();

