# Installation & Setup Verification

Complete setup guide with step-by-step verification.

---

## System Requirements

### Minimum Requirements
- Python 3.8 or higher
- 512 MB RAM
- 100 MB disk space
- Internet connection (for market data)
- Modern web browser (Chrome, Firefox, Safari, Edge)

### Recommended Specifications
- Python 3.10 or higher
- 2 GB RAM
- 500 MB disk space
- High-speed internet (< 50ms latency)
- Latest browser version

---

## Installation Steps

### Step 1: Verify Python Installation

Open terminal/command prompt and check Python version:

```bash
python --version
```

Expected output: `Python 3.8.x` or higher

If Python is not installed:
1. Download from https://www.python.org/downloads/
2. Install with default settings
3. **IMPORTANT**: Check "Add Python to PATH" during installation
4. Restart terminal/command prompt

**Verification:**
```bash
python --version
python -m pip --version
```

### Step 2: Clone/Extract Project

Extract the project folder to a location like:
- Windows: `C:\Users\YourName\Desktop\trading-signal-system`
- macOS: `~/Desktop/trading-signal-system`
- Linux: `~/trading-signal-system`

Navigate to project:
```bash
cd trading-signal-system
```

### Step 3: Backend Setup

#### Windows CMD/PowerShell:

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt

# Verify installation
pip list
```

#### macOS/Linux:

```bash
cd backend

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
pip list
```

**Expected packages after install:**
- fastapi (latest)
- uvicorn (latest)
- pydantic (latest)
- requests (latest)
- numpy (latest)

### Step 4: Start Backend Server

With virtual environment activated:

```bash
python app.py
```

Expected output:
```
2024-06-05 14:00:00,000 - root - INFO - Starting Trading Signal System on 0.0.0.0:8000
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Step 5: Verify Backend (in new terminal)

```bash
# Test health endpoint
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","timestamp":"2024-06-05 14:00:00","pairs_monitored":10}
```

### Step 6: Frontend Setup

In a new terminal/prompt:

```bash
cd frontend

# Windows
python -m http.server 3000

# macOS/Linux
python3 -m http.server 3000
```

Expected output:
```
Serving HTTP on 0.0.0.0 port 3000 (http://0.0.0.0:3000/) ...
```

### Step 7: Access Frontend

Open web browser and navigate to:
```
http://localhost:3000
```

Expected: Professional trading UI loads successfully

---

## Verification Checklist

### Backend Verification

- [ ] Python 3.8+ installed
- [ ] Virtual environment created and activated
- [ ] All dependencies installed (pip list shows packages)
- [ ] Backend starts without errors
- [ ] No permission errors or missing modules

### API Verification

Test each endpoint:

```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status":"healthy",...}

# Server time
curl http://localhost:8000/server-time
# Expected: {"server_time":"HH:MM:SS",...}

# Available pairs
curl http://localhost:8000/pairs
# Expected: {"pairs":["BTCUSDT","ETHUSDT",...]}

# System status
curl http://localhost:8000/status
# Expected: {"status":"operational",...}

# Generate signal
curl http://localhost:8000/signal
# Expected: {"pair":"...","direction":"CALL"/"PUT",...}
```

### Frontend Verification

- [ ] Frontend loads without errors (check F12 console)
- [ ] Server time displays and updates
- [ ] Status dot is green/connected
- [ ] "Get Best Signal" button is enabled
- [ ] No CORS errors in console

### Integration Verification

1. Click "Get Best Signal"
2. Verify response displays:
   - Trading pair name
   - Direction (CALL/PUT with color)
   - Confidence percentage
   - Entry and expiry times
   - Countdown timer
   - Indicator scores

---

## Troubleshooting Installation

### Python Not Found

**Error:** `'python' is not recognized as an internal or external command`

**Solution:**
```bash
# Check if installed
where python  # Windows
which python3  # macOS/Linux

# If not found, reinstall Python and add to PATH
# Windows: Run installer again, check "Add Python to PATH"
# macOS: brew install python3
# Linux: sudo apt-get install python3
```

### Virtual Environment Issues

**Error:** `No module named 'virtualenv'`

**Solution:**
```bash
python -m venv venv
# Don't use virtualenv, use built-in venv
```

### Dependency Installation Fails

**Error:** `ERROR: Could not find a version that satisfies the requirement`

**Solution:**
```bash
# Upgrade pip first
python -m pip install --upgrade pip

# Clear pip cache
pip cache purge

# Try installing again
pip install -r requirements.txt
```

### Port Already in Use

**Error:** `Address already in use`

**Solution - Windows:**
```bash
# Find process using port 8000
netstat -ano | findstr :8000

# Kill process (replace PID)
taskkill /PID 12345 /F

# Or use different port
python app.py --port 8001
```

**Solution - macOS/Linux:**
```bash
# Find process using port 8000
lsof -i :8000

# Kill process (replace PID)
kill -9 12345

# Or use different port
uvicorn app:app --port 8001
```

### CORS Error in Frontend

**Error:** `Access to XMLHttpRequest blocked by CORS policy`

**Solution:**
1. Verify backend is running on `http://localhost:8000`
2. Check `ALLOWED_ORIGINS` in `backend/config.py`
3. Verify frontend API URL in `frontend/app.js`:
   ```javascript
   const API_BASE_URL = 'http://localhost:8000';
   ```

### No Market Data

**Error:** `Market data unavailable`

**Solution:**
1. Verify internet connection
2. Check Binance API is accessible:
   ```bash
   curl https://api.binance.com/api/v3/time
   ```
3. Check for rate limiting (Binance has 1200 req/min limit)

---

## Configuration Verification

### Backend Configuration

Check `backend/config.py`:

```python
# Verify trading pairs
TRADING_PAIRS = [
    "BTCUSDT",
    "ETHUSDT",
    # ... should have 10 pairs
]

# Verify indicators configured
INDICATORS_CONFIG = {
    "RSI": {"period": 14, ...},
    "EMA": {"fast_period": 9, ...},
    "MACD": {"fast_period": 12, ...}
}

# Verify weights sum to 1.0
CONFIDENCE_WEIGHTS = {
    "rsi_signal": 0.30,
    "ema_trend": 0.30,
    "macd_confirmation": 0.20,
    "volume_strength": 0.20
}
# Total: 1.0 ✓

# Server settings
HOST = "0.0.0.0"
PORT = 8000
```

### Frontend Configuration

Check `frontend/app.js`:

```javascript
// Verify API URL
const API_BASE_URL = 'http://localhost:8000';

// Verify sync intervals
const SYNC_INTERVAL = 5000;  // 5 seconds
const COUNTDOWN_UPDATE_INTERVAL = 100;  // 100ms
const CACHE_UPDATE_INTERVAL = 60000;  // 60 seconds
```

---

## First Run Walkthrough

### Minute 1-2: Startup

1. Open first terminal, run: `run_backend.bat` (or manual steps)
2. Open second terminal, run: `run_frontend.bat` (or manual steps)
3. Open browser to `http://localhost:3000`

### Minute 2-5: Verification

1. Check header shows "Connected" status
2. Note current server time
3. Click "Get Best Signal"
4. Watch signal appear within 1-2 seconds

### Minute 5+: Normal Usage

1. Generate signals by clicking button
2. Review confidence and indicators
3. Watch countdown timer
4. Generate new signals as needed

---

## Performance Monitoring

### Backend Performance

Monitor in terminal window:

```
INFO:     127.0.0.1:55555 - "GET /signal HTTP/1.1" 200 OK
2024-06-05 14:31:42 - Signal generated in 0.234s
```

Look for:
- Response time: 50-350ms (50ms with cache, 350ms without)
- Status code: 200 (success)
- No error messages

### Frontend Performance

Open browser DevTools (F12):

1. **Console Tab**
   - No errors or warnings
   - Smooth time updates

2. **Network Tab**
   - API calls complete in < 200ms
   - No failed requests

3. **Performance**
   - Signal display: < 100ms
   - No jank in countdown

---

## Maintenance

### Regular Checks

- [ ] Python version: `python --version` (should be 3.8+)
- [ ] Backend logs: Look for errors on startup
- [ ] Frontend console: Check for warnings (F12)
- [ ] API responses: Should be consistent

### Periodic Tasks

**Weekly:**
- Clear browser cache
- Review backend logs for errors
- Test signal generation 5-10 times

**Monthly:**
- Update dependencies: `pip install --upgrade -r requirements.txt`
- Check Python version for updates
- Review configuration for optimization

---

## Environment Variables (Optional)

Create `backend/.env` file:

```
FLASK_ENV=production
API_TIMEOUT=10
CACHE_DURATION=30
LOG_LEVEL=INFO
```

---

## Docker Setup (Advanced)

For containerized deployment:

```dockerfile
# Dockerfile in backend/
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "app.py"]
```

Build and run:
```bash
docker build -t trading-signal .
docker run -p 8000:8000 trading-signal
```

---

## Next Steps After Successful Installation

1. **Read Documentation**
   - Open `README.md` for full documentation
   - Review `TECHNICAL.md` for implementation details

2. **Explore API**
   - Visit `http://localhost:8000/docs` for interactive API docs
   - Test all endpoints manually

3. **Customize Configuration**
   - Edit trading pairs in `backend/config.py`
   - Adjust indicator weights
   - Change cache duration

4. **Monitor Operations**
   - Keep terminal windows open
   - Watch for errors or warnings
   - Track performance metrics

---

## Support Resources

### Debugging

1. **Backend Logs**: Check terminal where backend is running
2. **Frontend Console**: Open F12 in browser, check console tab
3. **API Docs**: http://localhost:8000/docs for endpoint details

### Common Issues

1. **Backend won't start**: Check Python version and dependencies
2. **Frontend can't connect**: Verify backend is running and ports are correct
3. **No signals generating**: Check Binance API availability

### Getting Help

1. Check troubleshooting section above
2. Review TECHNICAL.md for implementation details
3. Check browser console for specific errors
4. Verify all prerequisites are installed

---

## Installation Complete!

Once you see the trading UI with a working signal generation, your installation is complete. You're ready to:

- Generate trading signals
- Analyze multiple pairs
- Study technical indicators
- Learn about algorithmic trading

Happy analyzing!
