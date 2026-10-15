# Trading Signal Generation System

A production-level, web-based system that generates 1-minute binary trading signals for analysis and education purposes. The system does NOT execute trades automatically.

---

## Overview

This system analyzes multiple cryptocurrency pairs using technical indicators (RSI, EMA, MACD, Volume) and generates trading signals for the NEXT candle, not the current candle. The signal includes:

- **Pair**: Most confident trading pair
- **Direction**: CALL (bullish) or PUT (bearish)
- **Entry Time**: When the signal becomes valid
- **Expiry Time**: When the signal expires (1 minute later)
- **Confidence**: Weighted score based on multiple indicators

---

## Architecture

### Backend (FastAPI)
Located in `backend/`

- **app.py**: Main FastAPI application with REST API endpoints
- **config.py**: Configuration and constants
- **market_data.py**: Binance API data fetching
- **indicators.py**: Technical indicator calculations
- **analysis.py**: Signal analysis and confidence scoring

### Frontend (Vanilla JavaScript)
Located in `frontend/`

- **index.html**: Main HTML structure
- **styles.css**: Responsive styling
- **app.js**: Frontend logic, API communication, countdown timer

---

## Project Structure

```
trading-signal-system/
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── market_data.py
│   ├── indicators.py
│   ├── analysis.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── README.md
```

---

## Installation & Setup

### Prerequisites
- Python 3.8+
- pip (Python package manager)
- Modern web browser

### Backend Setup

1. Navigate to backend directory:
```bash
cd backend
```

2. Create virtual environment:
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Start backend server:
```bash
python app.py
```

The backend will start on `http://localhost:8000`

Verify backend is running:
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### Frontend Setup

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Serve files using Python's built-in server:
```bash
# Python 3
python -m http.server 3000

# Python 2
python -m SimpleHTTPServer 3000
```

3. Open browser and navigate to:
```
http://localhost:3000
```

---

## Usage

### User Flow

1. **System Initialization**
   - Frontend syncs time with backend server
   - Status indicator shows "Connected"
   - "Get Best Signal" button becomes enabled

2. **Generate Signal**
   - Click "Get Best Signal" button
   - System fetches 1-minute candles for all pairs
   - Analyzes technical indicators
   - Selects pair with highest confidence
   - Calculates next candle times

3. **Signal Display**
   - Pair name and direction (CALL/PUT)
   - Confidence percentage
   - Current price
   - Entry and expiry times
   - Countdown timer to signal entry
   - Individual indicator scores

4. **Copy & Track**
   - Copy signal to clipboard
   - Generate new signal or wait for next candle
   - Countdown updates in real-time

---

## API Endpoints

### GET /signal
Generate best trading signal
```bash
curl http://localhost:8000/signal
```

Response:
```json
{
  "pair": "ETHUSDT",
  "direction": "CALL",
  "entry_time": "14:32:00",
  "expiry_time": "14:33:00",
  "confidence": "82%",
  "current_price": 2145.67,
  "indicator_scores": {
    "rsi": 72,
    "ema": 85,
    "macd": 65,
    "volume": 45
  },
  "generated_at": "14:31:23",
  "candle_duration": "1 minute"
}
```

### GET /server-time
Get current server time and next candle times
```bash
curl http://localhost:8000/server-time
```

Response:
```json
{
  "server_time": "14:31:23",
  "unix_timestamp": 1717862483,
  "next_candle_entry": "14:32:00",
  "next_candle_expiry": "14:33:00"
}
```

### GET /health
Health check
```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-06-05 14:31:23",
  "pairs_monitored": 10
}
```

### GET /pairs
Get available trading pairs
```bash
curl http://localhost:8000/pairs
```

### GET /status
Get system status and cache information
```bash
curl http://localhost:8000/status
```

---

## Technical Indicators

### RSI (Relative Strength Index)
- Period: 14
- Overbought: > 70 (bearish signal)
- Oversold: < 30 (bullish signal)
- Signal strength: 80% when triggered

### EMA (Exponential Moving Average)
- Fast EMA: 9 periods
- Slow EMA: 21 periods
- Crossover indicates trend change
- Signal strength: 70% for trends

### MACD (Moving Average Convergence Divergence)
- Fast: 12 periods
- Slow: 26 periods
- Signal: 9 periods
- Histogram crossover confirms trend
- Signal strength: 85% when confirmed

### Volume
- 14-period volume trend
- Strength measured against average volume
- Signal strength: 0-100% based on relative volume

---

## Confidence Scoring

Final confidence is calculated as weighted average:

```
Confidence = (RSI × 30%) + (EMA × 30%) + (MACD × 20%) + (Volume × 20%)
```

### Weights
- RSI Signal: 30%
- EMA Trend: 30%
- MACD Confirmation: 20%
- Volume Strength: 20%

### Signal Generation Logic

1. Each indicator provides a directional signal (CALL/PUT)
2. Direction is determined by majority vote
3. Confidence is combined from weighted scores
4. Pairs with confidence < 40% are flagged as low confidence

---

## Timing Logic - Critical Implementation

### Server-Side Calculation

The system uses **server time** (not client time) for accurate candle alignment:

```python
def calculate_next_candle_time(current_time):
    """
    Current: 02:36:23
    Next minute: (now + 1m).replace(seconds=0)
    Entry Time: 02:37:00
    Expiry Time: 02:38:00
    """
    next_minute = current_time.replace(second=0, microsecond=0)
    if current_time.second > 0 or current_time.microsecond > 0:
        next_minute += timedelta(minutes=1)
    
    return next_minute, next_minute + timedelta(minutes=1)
```

### Frontend Clock Sync

The frontend synchronizes its clock with the backend:

```javascript
let serverTimeOffset = 0;

async function syncServerTime() {
    const response = await fetch('/server-time');
    const data = await response.json();
    const serverTime = new Date(data.unix_timestamp * 1000);
    serverTimeOffset = serverTime - Date.now();
}

function getCurrentServerTime() {
    return new Date(Date.now() + serverTimeOffset);
}
```

---

## Configuration

Edit `backend/config.py` to customize:

### Trading Pairs
```python
TRADING_PAIRS = [
    "BTCUSDT",   # Bitcoin
    "ETHUSDT",   # Ethereum
    "BNBUSDT",   # Binance Coin
    # ... add more
]
```

### Technical Indicators
```python
INDICATORS_CONFIG = {
    "RSI": {"period": 14, "overbought": 70, "oversold": 30},
    "EMA": {"fast_period": 9, "slow_period": 21},
    "MACD": {"fast_period": 12, "slow_period": 26, "signal_period": 9}
}
```

### Data Fetching
```python
CANDLES_TO_FETCH = 100      # Number of candles to fetch
TIMEFRAME = "1m"             # Timeframe (1-minute)
MIN_CONFIDENCE_THRESHOLD = 40 # Minimum confidence for signals
```

### Cache Settings
```python
CACHE_DURATION_SECONDS = 30  # Cache duration before refreshing
```

---

## Market Data Source

The system uses **Binance Public API** (free, no authentication required):

- **Base URL**: https://api.binance.com/api/v3
- **Endpoint**: `/klines` (candlestick data)
- **Rate Limit**: 1200 requests per minute (sufficient for system)

### Data Fetched Per Pair
- 100 candles of 1-minute data
- Open, High, Low, Close, Volume
- Timestamp for each candle

---

## Error Handling

### Common Issues

**1. Connection Failed**
```
Error: "Failed to connect to server"
```
Solution: Ensure backend is running on http://localhost:8000

**2. Market Data Unavailable**
```
Error: "Market data unavailable. Please try again."
```
Solution: Binance API may be temporarily unavailable or rate limited

**3. No Viable Signals**
```
Error: "No viable signals generated"
```
Solution: All pairs may be below minimum confidence threshold (40%)

### Logging

Backend logs are printed to console:
```
2024-06-05 14:31:23 - root - INFO - Signal generated: ETHUSDT CALL at 14:31:23 (Confidence: 82%)
```

---

## Performance Considerations

### Backend
- **Cache Strategy**: Market data cached for 30 seconds
- **API Calls**: Max 1 call per pair per cache cycle
- **Processing**: ~200ms for full signal generation
- **Scalability**: Supports monitoring 10-50 pairs efficiently

### Frontend
- **Time Sync**: Every 5 seconds
- **Countdown Update**: Every 100ms (smooth animation)
- **No Memory Leaks**: Intervals cleared on visibility change

### Network
- **Latency**: <100ms typical for API calls
- **Bandwidth**: ~50KB per signal generation
- **Protocol**: HTTP/1.1 with CORS support

---

## Security Considerations

1. **No Credentials Stored**: System uses public APIs only
2. **CORS Protection**: Frontend and backend on different origins
3. **Input Validation**: All API inputs validated
4. **Error Handling**: No sensitive data in error messages
5. **HTTPS Ready**: Can be easily deployed with HTTPS

---

## Advanced Features

### Optional Enhancements

1. **WebSocket Updates**
   - Real-time market data streaming
   - Live indicator updates

2. **Multi-Timeframe Confirmation**
   - Analyze 1m + 5m timeframes
   - Higher confidence thresholds

3. **Signal History**
   - Log generated signals to database
   - Track accuracy over time

4. **Alert System**
   - Browser notifications when signal is generated
   - Email alerts (optional)

5. **Risk Management**
   - Position sizing calculator
   - Risk/reward ratio analysis

---

## Troubleshooting

### Backend Won't Start
```bash
# Check Python version
python --version  # Should be 3.8+

# Check if port is in use
netstat -an | grep 8000

# Verify dependencies
pip list | grep fastapi
```

### Frontend Can't Connect to Backend
```bash
# Check backend is running
curl http://localhost:8000/health

# Verify CORS is enabled
# Check browser console for CORS errors
# Ensure correct API_BASE_URL in app.js
```

### Slow Signal Generation
```bash
# Check network latency
time curl http://localhost:8000/signal

# Monitor CPU usage during analysis
# Reduce number of pairs if needed
# Increase cache duration
```

---

## Testing

### Manual Testing

1. **Signal Generation**
```bash
curl http://localhost:8000/signal | python -m json.tool
```

2. **Time Sync**
```bash
curl http://localhost:8000/server-time | python -m json.tool
```

3. **System Status**
```bash
curl http://localhost:8000/status | python -m json.tool
```

### Load Testing
```bash
# Generate 100 signals
for i in {1..100}; do
  curl http://localhost:8000/signal
  sleep 1
done
```

---

## Deployment

### Local Development
```bash
# Terminal 1: Start backend
cd backend
python app.py

# Terminal 2: Start frontend
cd frontend
python -m http.server 3000
```

### Production Deployment

1. **Backend** (using Gunicorn):
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

2. **Frontend** (using Nginx/Apache or GitHub Pages)
```bash
# Copy frontend files to web server
# Configure CORS headers
```

3. **Docker** (optional):
```dockerfile
FROM python:3.11
WORKDIR /app
COPY backend/ .
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
```

---

## License

Educational and research use only. Not for real trading without proper financial advisory.

---

## Support & Contact

For issues or questions:
1. Check the troubleshooting section
2. Review backend logs for errors
3. Check browser console for frontend errors
4. Verify Binance API is accessible

---

## Disclaimer

**IMPORTANT**: This system is designed for educational and analysis purposes only:

- Signals are NOT guaranteed to be profitable
- Past performance does NOT guarantee future results
- Always use proper risk management
- Never risk more than you can afford to lose
- Consult with financial advisors before trading
- The developers are NOT responsible for trading losses

This system demonstrates technical analysis concepts and API integration. It is NOT financial advice or a guarantee of profit.

---

## Version History

**v1.0.0** (2024-06-05)
- Initial release
- RSI, EMA, MACD, Volume indicators
- 1-minute signal generation
- Real-time countdown timer
- Responsive UI design
