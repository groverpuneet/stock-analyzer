// Stock Analyzer - Fear & Greed Widget for Scriptable
// Visual gauge display for India and US Fear & Greed Index
// Works in small and medium widget sizes

// ===== CONFIGURATION =====
const WEBAPP_URL = "https://avalanche-joining-yin.ngrok-free.dev";
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

function getColorHex(score) {
  if (score === null || score === undefined) return "#6b7280";
  if (score < 25) return "#dc2626";
  if (score < 45) return "#f97316";
  if (score < 55) return "#6b7280";
  if (score < 75) return "#84cc16";
  return "#22c55e";
}

function getLabel(score) {
  if (score === null || score === undefined) return "—";
  if (score < 25) return "Extreme Fear";
  if (score < 45) return "Fear";
  if (score < 55) return "Neutral";
  if (score < 75) return "Greed";
  return "Extreme Greed";
}

function getDirectionArrow(direction) {
  if (direction === "up") return "↑";
  if (direction === "down") return "↓";
  return "→";
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

// Fetch data from API
async function fetchFearGreed() {
  try {
    const req = new Request(API_ENDPOINT);
    req.timeoutInterval = 30;
    // Skip ngrok browser warning page
    req.headers = { "ngrok-skip-browser-warning": "true" };
    const data = await req.loadJSON();
    return data;
  } catch (e) {
    console.error("Failed to fetch Fear & Greed data:", e);
    return null;
  }
}

// Draw a semicircular gauge arc
function drawGauge(width, height, score, flag, direction) {
  const dc = new DrawContext();
  dc.size = new Size(width, height);
  dc.opaque = false;
  dc.respectScreenScale = true;

  const centerX = width / 2;
  const centerY = height * 0.55;
  const radius = Math.min(width, height) * 0.38;
  const lineWidth = radius * 0.18;

  const scoreVal = score !== null && score !== undefined ? score : 0;
  const scoreColor = new Color(getColorHex(score));
  const bgColor = new Color("#374151");

  // Draw background arc (full semicircle)
  dc.setStrokeColor(bgColor);
  dc.setLineWidth(lineWidth);

  const bgPath = new Path();
  const segments = 50;
  for (let i = 0; i <= segments; i++) {
    const angle = Math.PI + (i / segments) * Math.PI;
    const x = centerX + radius * Math.cos(angle);
    const y = centerY + radius * Math.sin(angle);
    if (i === 0) {
      bgPath.move(new Point(x, y));
    } else {
      bgPath.addLine(new Point(x, y));
    }
  }
  dc.addPath(bgPath);
  dc.strokePath();

  // Draw filled arc based on score (0-100)
  if (scoreVal > 0) {
    dc.setStrokeColor(scoreColor);
    dc.setLineWidth(lineWidth);

    const fillPath = new Path();
    const fillSegments = Math.floor((scoreVal / 100) * segments);
    for (let i = 0; i <= fillSegments; i++) {
      const angle = Math.PI + (i / segments) * Math.PI;
      const x = centerX + radius * Math.cos(angle);
      const y = centerY + radius * Math.sin(angle);
      if (i === 0) {
        fillPath.move(new Point(x, y));
      } else {
        fillPath.addLine(new Point(x, y));
      }
    }
    dc.addPath(fillPath);
    dc.strokePath();
  }

  // Draw flag emoji at top
  dc.setTextColor(Color.white());
  dc.setFont(Font.systemFont(width * 0.16));
  const flagSize = dc.getTextSize(flag);
  dc.drawText(flag, new Point(centerX - flagSize.width / 2, height * 0.02));

  // Draw score in center
  const scoreText = score !== null && score !== undefined ? Math.round(score).toString() : "—";
  dc.setTextColor(scoreColor);
  dc.setFont(Font.boldSystemFont(width * 0.22));
  const scoreSize = dc.getTextSize(scoreText);
  dc.drawText(scoreText, new Point(centerX - scoreSize.width / 2, centerY - scoreSize.height * 0.4));

  // Draw direction arrow next to score
  if (direction) {
    const arrow = getDirectionArrow(direction);
    const arrowColor = direction === "up" ? new Color("#22c55e") : direction === "down" ? new Color("#ef4444") : Color.gray();
    dc.setTextColor(arrowColor);
    dc.setFont(Font.systemFont(width * 0.14));
    dc.drawText(arrow, new Point(centerX + scoreSize.width / 2 + 2, centerY - scoreSize.height * 0.35));
  }

  // Draw label below arc
  const label = getLabel(score);
  dc.setTextColor(Color.white());
  dc.setFont(Font.systemFont(width * 0.1));
  const labelSize = dc.getTextSize(label);
  dc.drawText(label, new Point(centerX - labelSize.width / 2, centerY + radius * 0.35));

  return dc.getImage();
}

// Create small widget with single gauge (India) + US as text
function createSmallWidget(data) {
  const widget = new ListWidget();

  const indiaScore = data?.india?.score;
  const usScore = data?.us?.score;

  widget.backgroundGradient = getBackgroundGradient(indiaScore, usScore);
  widget.setPadding(8, 8, 8, 8);

  // Draw India gauge
  const gaugeImage = drawGauge(140, 100, indiaScore, "🇮🇳", data?.india?.direction);

  const gaugeStack = widget.addStack();
  gaugeStack.layoutHorizontally();
  gaugeStack.addSpacer();
  const img = gaugeStack.addImage(gaugeImage);
  img.imageSize = new Size(140, 100);
  gaugeStack.addSpacer();

  widget.addSpacer(2);

  // US score as small text below
  const usRow = widget.addStack();
  usRow.layoutHorizontally();
  usRow.addSpacer();

  if (data?.us) {
    const usFlag = usRow.addText("🇺🇸 ");
    usFlag.font = Font.systemFont(10);

    const usScoreText = usRow.addText(`${data.us.score || "—"}`);
    usScoreText.font = Font.boldSystemFont(12);
    usScoreText.textColor = getColor(data.us.score);

    const usArrow = usRow.addText(` ${getDirectionArrow(data.us.direction)}`);
    usArrow.font = Font.systemFont(10);
    usArrow.textColor = data.us.direction === "up" ? new Color("#22c55e") : data.us.direction === "down" ? new Color("#ef4444") : Color.gray();
  } else {
    const noData = usRow.addText("🇺🇸 —");
    noData.font = Font.systemFont(10);
    noData.textColor = Color.gray();
  }

  usRow.addSpacer();

  widget.addSpacer(null);

  // Footer with time
  const footer = widget.addStack();
  footer.layoutHorizontally();
  footer.addSpacer();
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const updateText = footer.addText(timeStr);
  updateText.font = Font.systemFont(8);
  updateText.textColor = Color.white();
  updateText.textOpacity = 0.5;
  footer.addSpacer();

  widget.url = WEBAPP_URL;
  widget.refreshAfterDate = new Date(Date.now() + 30 * 60 * 1000);

  return widget;
}

// Create medium widget with two gauges side by side
function createMediumWidget(data) {
  const widget = new ListWidget();

  const indiaScore = data?.india?.score;
  const usScore = data?.us?.score;

  widget.backgroundGradient = getBackgroundGradient(indiaScore, usScore);
  widget.setPadding(10, 10, 10, 10);

  // Header
  const header = widget.addStack();
  header.layoutHorizontally();
  header.addSpacer();
  const headerText = header.addText("Fear & Greed Index");
  headerText.font = Font.boldSystemFont(12);
  headerText.textColor = Color.white();
  headerText.textOpacity = 0.8;
  header.addSpacer();

  widget.addSpacer(4);

  // Two gauges side by side
  const gaugeRow = widget.addStack();
  gaugeRow.layoutHorizontally();

  // India gauge
  const indiaGauge = drawGauge(150, 110, indiaScore, "🇮🇳", data?.india?.direction);
  const indiaImg = gaugeRow.addImage(indiaGauge);
  indiaImg.imageSize = new Size(150, 110);

  gaugeRow.addSpacer();

  // US gauge
  const usGauge = drawGauge(150, 110, usScore, "🇺🇸", data?.us?.direction);
  const usImg = gaugeRow.addImage(usGauge);
  usImg.imageSize = new Size(150, 110);

  widget.addSpacer(null);

  // Footer
  const footer = widget.addStack();
  footer.layoutHorizontally();

  const dataDate = data?.india?.date || data?.us?.date || "";
  const dateText = footer.addText(`Data: ${dataDate}`);
  dateText.font = Font.systemFont(9);
  dateText.textColor = Color.white();
  dateText.textOpacity = 0.5;

  footer.addSpacer();

  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const updateText = footer.addText(`Updated: ${timeStr}`);
  updateText.font = Font.systemFont(9);
  updateText.textColor = Color.white();
  updateText.textOpacity = 0.5;

  widget.url = WEBAPP_URL;
  widget.refreshAfterDate = new Date(Date.now() + 30 * 60 * 1000);

  return widget;
}

// Main
async function main() {
  const data = await fetchFearGreed();

  let widget;

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
