# Pocket Option Integration Guide

Complete guide to using the Trading Signal System with Pocket Option session tokens.

---

## Overview

The system now supports **both Binance and Pocket Option** as data sources with automatic session management that keeps your session token active even during inactivity.

### Features

- ✅ **Session Keep-Alive**: Background thread refreshes token every 5 minutes
- ✅ **Auto-Reconnect**: Handles session expiry gracefully
- ✅ **Multiple Data Sources**: Switch between Binance and Pocket Option
- ✅ **Same Signal Quality**: Identical indicator calculations
- ✅ **No Auto-Trading**: Signal generation only (manual entry required)

---

## Getting Your Pocket Option Session Token

### Step 1: Log into Pocket Option

Go to [Pocket Option](https://pocketoption.com) and log in with your credentials.

### Step 2: Open Developer Tools

In your browser:
- **Chrome/Firefox**: Press `F12`
- **Safari**: Enable Developer Tools in Preferences, then press `Cmd+Option+I`
- **Edge**: Press `F12`

### Step 3: Find Your Session Token

Navigate to one of these locations:

#### Option A: Application/Storage Tab
1. Click **Application** or **Storage** tab
2. Expand **Cookies**
3. Find **pocketoption.com** domain
4. Look for cookies like:
   - `session`
   - `token`
   - `auth_token`
   - `access_token`

#### Option B: Network Tab
1. Click **Network** tab
2. Perform any action in Pocket Option (generate a quote, etc.)
3. Look for API requests to `api.pocketoption.com`
4. Check the **Authorization header** in the request
5. Copy the token value (usually starts with `Bearer ` or is a long alphanumeric string)

#### Option C: Local Storage
1. Click **Application** or **Storage** tab
2. Expand **Local Storage**
3. Find **pocketoption.com** domain
4. Look for `token` or `session_token` key

### Step 4: Copy Your Token

Copy the entire token value. It should look like:
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
```

---

## Starting the System with Pocket Option

### Step 1: Start Backend

```bash
cd trading-signal-system/backend
python app.py
```

You should see:
```
Starting Trading Signal System on 0.0.0.0:8000
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 2: Start Frontend

In a new terminal:
```bash
cd trading-signal-system/frontend
python -m http.server 3000
```

You should see:
```
Serving HTTP on :: port 3000
```

### Step 3: Configure Data Source

Use the API to switch to Pocket Option. Send this request:

```bash
curl -X POST http://localhost:8000/config/data-source \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "pocket_option",
    "session_token": "YOUR_POCKET_OPTION_TOKEN_HERE"
  }'
```

Replace `YOUR_POCKET_OPTION_TOKEN_HERE` with your actual token.

**Expected Response:**
```json
{
  "status": "success",
  "message": "Switched to Pocket Option API",
  "data_source": "pocket_option",
  "session_status": {
    "active": true,
    "age_seconds": 0,
    "last_activity": "2026-06-05T02:53:00",
    "created_at": "2026-06-05T02:53:00"
  }
}
```

### Step 4: Check Status

Verify the system is using Pocket Option:

```bash
curl http://localhost:8000/status
```

You should see:
```json
{
  "status": "operational",
  "data_source": "pocket_option",
  "cache_valid": true,
  "cache_age_seconds": 5,
  "cached_items": 23,
  "session_status": {
    "active": true,
    "age_seconds": 10,
    ...
  }
}
```

---

## Using the Frontend

### Access the UI

Open your browser to:
```
http://localhost:3000
```

### Check Connection Status

- **Green dot**: Connected to Pocket Option (session active)
- **Red dot**: Disconnected
- **Yellow dot**: Connecting

### Generate Signals

1. Click **"Get Best Signal"** button
2. System analyzes Pocket Option assets
3. Returns best signal for the next candle

### Signal Details

Signals include:
- **Asset**: EUR/USD, Gold, S&P 500, Bitcoin, etc.
- **Direction**: CALL (bullish) or PUT (bearish)
- **Confidence**: Percentage (0-100%)
- **Entry & Expiry**: Times for the 1-minute candle
- **Indicator Scores**: RSI, EMA, MACD, Volume
- **Current Price**: Live price from Pocket Option
- **Data Source**: Shows "Pocket Option"

---

## Session Management

### Automatic Keep-Alive

The system automatically:
- Refreshes your session token every **5 minutes**
- Prevents token expiry due to inactivity
- Maintains active connection in background
- Handles reconnection on failure

### Monitor Session Status

Check your session health:

```bash
curl http://localhost:8000/status
```

Look for:
```json
"session_status": {
  "active": true,
  "age_seconds": 600,
  "last_activity": "2026-06-05T03:10:00",
  "created_at": "2026-06-05T02:53:00"
}
```

- **active**: Session is alive
- **age_seconds**: How long session has been active
- **last_activity**: Last API call to Pocket Option
- **created_at**: When session was established

---

## Available Assets

The system monitors **23 Pocket Option assets** across 4 categories:

### Forex Pairs (10)
- EUR/USD, GBP/USD, USD/JPY, AUD/USD
- USD/CAD, USD/CHF, NZD/USD, EUR/GBP
- EUR/JPY, GBP/JPY

### Commodities (3)
- XAU/USD (Gold)
- XAG/USD (Silver)
- WTI (Oil)

### Cryptocurrencies (3)
- BTC/USD
- ETH/USD
- XRP/USD

### Indices (4)
- SPX500 (S&P 500)
- DAX (German DAX)
- FTSE (FTSE 100)
- (Additional based on your subscription)

See available assets:
```bash
curl http://localhost:8000/pairs
```

---

## API Endpoints

### Configuration

**POST /config/data-source**
- Switch between Binance and Pocket Option
- Requires session token for Pocket Option

```bash
curl -X POST http://localhost:8000/config/data-source \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "pocket_option",
    "session_token": "YOUR_TOKEN"
  }'
```

### Data

**GET /signal**
- Generate trading signal
- Uses current data source (Binance or Pocket Option)
- Response includes `data_source` field

**GET /server-time**
- Get current server time from data source
- Returns next candle entry/expiry times

**GET /pairs**
- List available assets for current data source

**GET /data-source**
- Get current data source configuration
- Shows session status if Pocket Option

**GET /status**
- System status and cache information
- Shows session keep-alive status

**GET /health**
- Health check with session information

**POST /update-cache**
- Manually refresh market data

---

## Switching Data Sources

### From Binance to Pocket Option

```bash
curl -X POST http://localhost:8000/config/data-source \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "pocket_option",
    "session_token": "YOUR_TOKEN"
  }'
```

### From Pocket Option to Binance

```bash
curl -X POST http://localhost:8000/config/data-source \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "binance"
  }'
```

---

## Troubleshooting

### Session Token Expired

**Error**: `{"detail": "Invalid session token"}`

**Solution**:
1. Get a new token (follow steps above)
2. Reconfigure data source with new token
```bash
curl -X POST http://localhost:8000/config/data-source \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "pocket_option",
    "session_token": "NEW_TOKEN"
  }'
```

### Session Not Staying Active

**Issue**: Session still expires despite keep-alive

**Solution**:
1. Check backend logs for errors
2. Verify token is correct
3. Try getting new token from Pocket Option
4. Ensure backend is running (don't close terminal)

### Can't Find Token

**Issue**: Can't locate session token in browser

**Solution**:
1. Make sure you're logged into Pocket Option
2. Check correct domain (pocketoption.com)
3. Clear browser cache and log in again
4. Try different browsers (Chrome usually works best)
5. Check Network tab while making an API call

### Frontend Shows "Disconnected"

**Issue**: Red status dot in UI

**Solution**:
1. Check backend is running: `curl http://localhost:8000/health`
2. Check session status: `curl http://localhost:8000/status`
3. Verify token is valid: `curl http://localhost:8000/data-source`
4. Restart with new token if needed

### No Signals Generated

**Issue**: System says "No viable signals generated"

**Error**: Likely Pocket Option API temporarily unavailable

**Solution**:
1. Check logs in backend terminal
2. Verify Pocket Option website is accessible
3. Try manual cache update: `curl -X POST http://localhost:8000/update-cache`
4. Wait 30 seconds and try again

---

## Performance Notes

### Pocket Option Integration Performance

- **Signal Generation**: 1-3 seconds (slower than Binance due to API)
- **Data Fetch**: 200-500ms per asset
- **Session Keep-Alive**: Negligible overhead (5 second interval)
- **Memory Usage**: 50-100MB (same as Binance)

### Recommendations

1. **Cache Duration**: Keep at 30 seconds
2. **Keep-Alive Interval**: 5 minutes is optimal
3. **Session Timeout**: 1 hour is safe
4. **Number of Assets**: Pocket Option has more pairs than Binance

---

## Security Considerations

### Token Safety

⚠️ **Important**: Your session token is sensitive!

- Don't share it with anyone
- Don't commit it to version control
- Don't post it in forums or chat
- Keep backend running on localhost only
- Use environment variables for production

### Environment Variables (Optional)

Create `.env` file in backend:
```
POCKET_OPTION_TOKEN=YOUR_TOKEN_HERE
```

Then update Python to load from environment:
```python
from os import getenv
token = getenv('POCKET_OPTION_TOKEN')
```

---

## Testing Configuration

### Quick Test Flow

1. **Terminal 1**: Start backend
2. **Terminal 2**: Start frontend
3. **Terminal 3**: Configure data source
```bash
curl -X POST http://localhost:8000/config/data-source \
  -H "Content-Type: application/json" \
  -d '{"data_source": "pocket_option", "session_token": "YOUR_TOKEN"}'
```

4. **Browser**: Open http://localhost:3000
5. **Click**: "Get Best Signal"
6. **Observe**: Signal with Pocket Option data source

### Verify Everything Works

```bash
# Check health
curl http://localhost:8000/health

# Get available assets
curl http://localhost:8000/pairs

# Get system status
curl http://localhost:8000/status

# Generate signal
curl http://localhost:8000/signal
```

---

## Next Steps

1. ✅ Get your session token
2. ✅ Start backend and frontend
3. ✅ Configure Pocket Option data source
4. ✅ Generate your first signal
5. ✅ Monitor session status
6. ✅ Generate signals manually or via API

---

## Support

For issues:

1. Check backend terminal logs for errors
2. Verify token is current (not expired)
3. Try switching to Binance to verify system works
4. Check status endpoint for session information
5. Review troubleshooting section above

---

You're ready to generate trading signals from Pocket Option! 📊
