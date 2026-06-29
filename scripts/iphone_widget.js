// Stock Analyzer - Fear & Greed Widget for Scriptable
// Shows India and US Fear & Greed Index scores
// Works in small and medium widget sizes

// ===== CONFIGURATION =====
// Replace with your Cloudflare tunnel URL
const WEBAPP_URL = "https://expiration-event-hindu-updating.trycloudflare.com";
// =========================

const API_ENDPOINT = `${WEBAPP_URL}/api/fear-greed`;

// Color scheme based on score
function getColor(score) {
  if (score === null || score === undefined) return Color.gray();
  if (score < 25) return new Color("#dc2626"); // Extreme Fear - red
  if (score < 45) return new Color("#f97316"); // Fear - orange
  if (score < 55) return new Color("#6b7280"); // Neutral - grey
  if (score < 75) return new Color("#84cc16"); // Greed - light green
  return new Color("#22c55e"); // Extreme Greed - green
}

function getBackgroundGradient(indiaScore, usScore) {
  const avgScore = ((indiaScore || 50) + (usScore || 50)) / 2;
  const gradient = new LinearGradient();
  gradient.locations = [0, 1];

  if (avgScore < 25) {
    gradient.colors = [new Color("#450a0a"), new Color("#7f1d1d")];
  } else if (avgScore < 45) {
    gradient.colors = [new Color("#431407"), new Color("#7c2d12")];
  } else if (avgScore < 55) {
    gradient.colors = [new Color("#1f2937"), new Color("#374151")];
  } else if (avgScore < 75) {
    gradient.colors = [new Color("#14532d"), new Color("#166534")];
  } else {
    gradient.colors = [new Color("#052e16"), new Color("#14532d")];
  }
  return gradient;
}

function getDirectionArrow(direction) {
  if (direction === "up") return "↑";
  if (direction === "down") return "↓";
  return "→";
}

// Fetch data from API
async function fetchFearGreed() {
  try {
    const req = new Request(API_ENDPOINT);
    req.timeoutInterval = 30;
    const data = await req.loadJSON();
    return data;
  } catch (e) {
    console.error("Failed to fetch Fear & Greed data:", e);
    return null;
  }
}

// Create small widget
function createSmallWidget(data) {
  const widget = new ListWidget();

  const indiaScore = data?.india?.score;
  const usScore = data?.us?.score;

  widget.backgroundGradient = getBackgroundGradient(indiaScore, usScore);
  widget.setPadding(12, 12, 12, 12);

  // Header
  const header = widget.addStack();
  header.layoutHorizontally();
  const headerText = header.addText("📈 Fear & Greed");
  headerText.font = Font.boldSystemFont(11);
  headerText.textColor = Color.white();

  widget.addSpacer(6);

  // India row
  const indiaStack = widget.addStack();
  indiaStack.layoutHorizontally();
  indiaStack.centerAlignContent();

  const indiaFlag = indiaStack.addText("🇮🇳 ");
  indiaFlag.font = Font.systemFont(14);

  if (data?.india) {
    const indiaScoreText = indiaStack.addText(`${data.india.score || "—"}`);
    indiaScoreText.font = Font.boldSystemFont(18);
    indiaScoreText.textColor = getColor(data.india.score);

    indiaStack.addSpacer(4);

    const indiaLabel = indiaStack.addText(`${data.india.label || ""} ${getDirectionArrow(data.india.direction)}`);
    indiaLabel.font = Font.systemFont(11);
    indiaLabel.textColor = Color.white();
    indiaLabel.textOpacity = 0.85;
  } else {
    const noData = indiaStack.addText("—");
    noData.font = Font.systemFont(14);
    noData.textColor = Color.gray();
  }

  widget.addSpacer(4);

  // US row
  const usStack = widget.addStack();
  usStack.layoutHorizontally();
  usStack.centerAlignContent();

  const usFlag = usStack.addText("🇺🇸 ");
  usFlag.font = Font.systemFont(14);

  if (data?.us) {
    const usScoreText = usStack.addText(`${data.us.score || "—"}`);
    usScoreText.font = Font.boldSystemFont(18);
    usScoreText.textColor = getColor(data.us.score);

    usStack.addSpacer(4);

    const usLabel = usStack.addText(`${data.us.label || ""} ${getDirectionArrow(data.us.direction)}`);
    usLabel.font = Font.systemFont(11);
    usLabel.textColor = Color.white();
    usLabel.textOpacity = 0.85;
  } else {
    const noData = usStack.addText("—");
    noData.font = Font.systemFont(14);
    noData.textColor = Color.gray();
  }

  widget.addSpacer(null);

  // Updated timestamp
  const footer = widget.addStack();
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const updateText = footer.addText(`Updated: ${timeStr}`);
  updateText.font = Font.systemFont(9);
  updateText.textColor = Color.white();
  updateText.textOpacity = 0.6;

  // Tap to open webapp
  widget.url = WEBAPP_URL;

  // Refresh in 30 minutes (iOS minimum ~15 min)
  widget.refreshAfterDate = new Date(Date.now() + 30 * 60 * 1000);

  return widget;
}

// Draw mini sparkline
function drawSparkline(drawContext, history, x, y, width, height, color) {
  if (!history || history.length < 2) return;

  const scores = history.map(h => h.score).filter(s => s !== null);
  if (scores.length < 2) return;

  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);
  const range = maxScore - minScore || 1;

  const points = scores.map((score, i) => ({
    x: x + (i / (scores.length - 1)) * width,
    y: y + height - ((score - minScore) / range) * height
  }));

  const path = new Path();
  path.move(new Point(points[0].x, points[0].y));
  for (let i = 1; i < points.length; i++) {
    path.addLine(new Point(points[i].x, points[i].y));
  }

  drawContext.setStrokeColor(color);
  drawContext.setLineWidth(1.5);
  drawContext.addPath(path);
  drawContext.strokePath();
}

// Create medium widget with sparklines
function createMediumWidget(data) {
  const widget = new ListWidget();

  const indiaScore = data?.india?.score;
  const usScore = data?.us?.score;

  widget.backgroundGradient = getBackgroundGradient(indiaScore, usScore);
  widget.setPadding(14, 14, 14, 14);

  // Header
  const header = widget.addStack();
  header.layoutHorizontally();
  const headerText = header.addText("📈 Fear & Greed Index");
  headerText.font = Font.boldSystemFont(13);
  headerText.textColor = Color.white();
  header.addSpacer();

  widget.addSpacer(8);

  // Main content - two columns
  const mainStack = widget.addStack();
  mainStack.layoutHorizontally();

  // Left column - India
  const indiaCol = mainStack.addStack();
  indiaCol.layoutVertically();
  indiaCol.size = new Size(140, 0);

  const indiaHeader = indiaCol.addStack();
  indiaHeader.layoutHorizontally();
  const indiaFlag = indiaHeader.addText("🇮🇳 India");
  indiaFlag.font = Font.boldSystemFont(12);
  indiaFlag.textColor = Color.white();

  indiaCol.addSpacer(2);

  if (data?.india) {
    const indiaScoreRow = indiaCol.addStack();
    indiaScoreRow.layoutHorizontally();
    indiaScoreRow.centerAlignContent();

    const indiaScoreText = indiaScoreRow.addText(`${data.india.score || "—"}`);
    indiaScoreText.font = Font.boldSystemFont(28);
    indiaScoreText.textColor = getColor(data.india.score);

    indiaScoreRow.addSpacer(6);

    const indiaArrow = indiaScoreRow.addText(getDirectionArrow(data.india.direction));
    indiaArrow.font = Font.systemFont(20);
    indiaArrow.textColor = data.india.direction === "up" ? new Color("#22c55e") : data.india.direction === "down" ? new Color("#ef4444") : Color.gray();

    const indiaLabel = indiaCol.addText(data.india.label || "");
    indiaLabel.font = Font.systemFont(11);
    indiaLabel.textColor = Color.white();
    indiaLabel.textOpacity = 0.8;

    // Sparkline placeholder (draw at end)
    indiaCol.addSpacer(4);
    const sparkPlaceholder1 = indiaCol.addStack();
    sparkPlaceholder1.size = new Size(110, 20);
  }

  mainStack.addSpacer();

  // Right column - US
  const usCol = mainStack.addStack();
  usCol.layoutVertically();
  usCol.size = new Size(140, 0);

  const usHeader = usCol.addStack();
  usHeader.layoutHorizontally();
  const usFlag = usHeader.addText("🇺🇸 US");
  usFlag.font = Font.boldSystemFont(12);
  usFlag.textColor = Color.white();

  usCol.addSpacer(2);

  if (data?.us) {
    const usScoreRow = usCol.addStack();
    usScoreRow.layoutHorizontally();
    usScoreRow.centerAlignContent();

    const usScoreText = usScoreRow.addText(`${data.us.score || "—"}`);
    usScoreText.font = Font.boldSystemFont(28);
    usScoreText.textColor = getColor(data.us.score);

    usScoreRow.addSpacer(6);

    const usArrow = usScoreRow.addText(getDirectionArrow(data.us.direction));
    usArrow.font = Font.systemFont(20);
    usArrow.textColor = data.us.direction === "up" ? new Color("#22c55e") : data.us.direction === "down" ? new Color("#ef4444") : Color.gray();

    const usLabel = usCol.addText(data.us.label || "");
    usLabel.font = Font.systemFont(11);
    usLabel.textColor = Color.white();
    usLabel.textOpacity = 0.8;
  }

  widget.addSpacer(null);

  // Footer with date
  const footer = widget.addStack();
  footer.layoutHorizontally();

  const dataDate = data?.india?.date || data?.us?.date || "";
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const dateText = footer.addText(`Data: ${dataDate}`);
  dateText.font = Font.systemFont(9);
  dateText.textColor = Color.white();
  dateText.textOpacity = 0.6;

  footer.addSpacer();

  const updateText = footer.addText(`Updated: ${timeStr}`);
  updateText.font = Font.systemFont(9);
  updateText.textColor = Color.white();
  updateText.textOpacity = 0.6;

  widget.url = WEBAPP_URL;
  widget.refreshAfterDate = new Date(Date.now() + 30 * 60 * 1000);

  return widget;
}

// Main
async function main() {
  const data = await fetchFearGreed();

  let widget;

  // Check widget family (small or medium)
  if (config.widgetFamily === "medium") {
    widget = createMediumWidget(data);
  } else {
    widget = createSmallWidget(data);
  }

  if (config.runsInWidget) {
    Script.setWidget(widget);
  } else {
    // Preview in Scriptable app
    if (config.widgetFamily === "medium") {
      widget.presentMedium();
    } else {
      widget.presentSmall();
    }
  }

  Script.complete();
}

await main();
