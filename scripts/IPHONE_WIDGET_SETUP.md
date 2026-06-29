# iPhone Fear & Greed Widget Setup

This widget displays India and US Fear & Greed Index scores on your iPhone home screen using the **Scriptable** app.

## Prerequisites

- iPhone with iOS 14+
- Stock Analyzer backend running with Cloudflare Tunnel

## Permanent Tunnel URL

The ngrok static domain is permanent and never changes:

```
https://avalanche-joining-yin.ngrok-free.dev
```

## Setup Instructions

### 1. Install Scriptable

Download **Scriptable** from the App Store (free):
https://apps.apple.com/app/scriptable/id1405459188

### 2. Create the Script

1. Open Scriptable
2. Tap the **+** button in the top right
3. Paste the contents of `iphone_widget.js`
4. The permanent URL is already configured:
   ```javascript
   const WEBAPP_URL = "https://avalanche-joining-yin.ngrok-free.dev";
   ```
5. Tap the script name at the top and rename it to "Fear & Greed"
6. Tap **Done**

### 3. Test the Script

1. Tap the **▶** (play) button to run the script
2. You should see a preview of the widget with current F&G scores
3. If you see "—" for scores, check:
   - Is the tunnel running? (`launchctl list | grep tunnel`)
   - Is the backend running? (`curl http://localhost:8009/api/fear-greed`)
   - Is the URL correct in the script?

### 4. Add Widget to Home Screen

1. Long-press on your iPhone home screen until apps jiggle
2. Tap the **+** button (top left corner)
3. Search for "Scriptable"
4. Choose **Small** or **Medium** size:
   - Small: Shows scores, labels, and direction arrows
   - Medium: Shows more detail with larger scores
5. Tap "Add Widget"
6. Long-press the new widget → "Edit Widget"
7. Set **Script** to "Fear & Greed"
8. Set **When Interacting** to "Run Script" (optional — lets you tap to refresh)

### 5. Done!

The widget will:
- Show India 🇮🇳 and US 🇺🇸 Fear & Greed scores
- Color-code based on market sentiment (red = fear, green = greed)
- Show direction arrows (↑ ↓ →)
- Auto-refresh approximately every 30 minutes
- Open the full webapp when tapped

## Widget Sizes

### Small Widget
```
┌─────────────────────┐
│ 📈 Fear & Greed     │
│ 🇮🇳 67 Greed ↑      │
│ 🇺🇸 71 Greed ↑      │
│ Updated: 2:30 PM    │
└─────────────────────┘
```

### Medium Widget
```
┌─────────────────────────────────────────┐
│ 📈 Fear & Greed Index                   │
│                                         │
│ 🇮🇳 India          🇺🇸 US               │
│ 67 ↑               71 ↑                 │
│ Greed              Greed                │
│                                         │
│ Data: 2026-06-28       Updated: 2:30 PM │
└─────────────────────────────────────────┘
```

## Color Legend

| Score Range | Label         | Color       |
|-------------|---------------|-------------|
| 0-24        | Extreme Fear  | Red         |
| 25-44       | Fear          | Orange      |
| 45-54       | Neutral       | Grey        |
| 55-74       | Greed         | Light Green |
| 75-100      | Extreme Greed | Green       |

## Troubleshooting

### Widget shows "—" for scores

1. **Tunnel not running:**
   ```bash
   launchctl list | grep tunnel
   # If missing: launchctl load ~/Library/LaunchAgents/com.stockanalyzer.tunnel.plist
   ```

2. **Backend not running:**
   ```bash
   curl http://localhost:8009/api/fear-greed
   # If error: launchctl start com.stockanalyzer.backend
   ```

3. **Check tunnel logs:**
   ```bash
   tail -20 ~/stock-analyzer/logs/tunnel.error.log
   ```

### Widget not refreshing

iOS limits widget refresh frequency. The widget requests a 30-minute refresh, but iOS may delay it based on:
- Battery level
- How often you view the widget
- Background app refresh settings

To force refresh: tap the widget (if "Run Script" is set) or open Scriptable and run the script manually.

## Files

- `iphone_widget.js` — The Scriptable widget code
- `~/Library/LaunchAgents/com.stockanalyzer.tunnel.plist` — ngrok tunnel launchd config
- `~/stock-analyzer/logs/tunnel.log` — Tunnel output log
- `~/stock-analyzer/logs/tunnel.error.log` — Tunnel status log
