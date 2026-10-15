# Quick Start Guide

Get the Trading Signal System running in 5 minutes!

---

## Prerequisites

- **Python 3.8+** - [Download](https://www.python.org/downloads/)
- **Modern Web Browser** - Chrome, Firefox, Safari, or Edge
- **Internet Connection** - For market data fetching

Verify Python installation:
```bash
python --version
```

---

## Option 1: Automatic Startup (Windows)

### Step 1: Start Backend
Double-click `run_backend.bat` in the project root folder.

You should see:
```
Starting Backend Server...
Backend will start on http://localhost:8000
```

### Step 2: Start Frontend (in a new terminal/prompt)
Double-click `run_frontend.bat` in the project root folder.

You should see:
```
Starting Frontend Server...
Frontend will start on http://localhost:3000
```

### Step 3: Open in Browser
Navigate to: http://localhost:3000

---

## Option 2: Manual Startup (macOS/Linux)

### Step 1: Backend Setup
```bash
cd backend

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start server
python app.py
```

Backend should start on: http://localhost:8000

### Step 2: Frontend Setup (in a new terminal)
```bash
cd frontend
python3 -m http.server 3000
```

Frontend should start on: http://localhost:3000

### Step 3: Open in Browser
Navigate to: http://localhost:3000

---

## Option 3: Manual Startup (Windows PowerShell/CMD)

### Step 1: Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
python app.py
```

### Step 2: Frontend (new terminal)
```bash
cd frontend
python -m http.server 3000
```

### Step 3: Browser
Go to: http://localhost:3000

---

## First Signal Generation

1. **Wait for "Connected" Status**
   - Green dot should appear in header
   - "Get Best Signal" button should be enabled

2. **Click "Get Best Signal"**
   - System analyzes all 10 trading pairs
   - Takes ~1-2 seconds

3. **Review Signal**
   - Pair with highest confidence
   - Direction (CALL or PUT)
   - Entry and expiry times
   - Countdown timer to entry

4. **Copy & Track** (Optional)
   - Click "Copy Signal" to clipboard
   - Generate new signal or wait for next candle

---

## Troubleshooting

### Backend Won't Start
```
Error: No module named 'fastapi'
```
Solution: Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### Frontend Won't Connect
```
Error: Failed to connect to server
```
Solution:
1. Verify backend is running: http://localhost:8000/health
2. Check browser console (F12) for CORS errors
3. Verify API_BASE_URL in frontend/app.js is correct

### Port Already in Use
```
Error: Address already in use
```
Solution: Change ports in scripts or kill process:
```bash
# Windows: Find and kill process on port
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# macOS/Linux: Kill process on port
lsof -i :8000
kill -9 <PID>
```

---

## Verification Checklist

- [ ] Python 3.8+ installed
- [ ] Backend running on http://localhost:8000
- [ ] Frontend running on http://localhost:3000
- [ ] Browser shows "Connected" status
- [ ] "Get Best Signal" button is enabled
- [ ] First signal generated successfully

---

## Typical Signal Output

```
Pair: ETHUSDT
Direction: CALL
Entry Time: 14:32:00
Expiry Time: 14:33:00
Confidence: 82%
Current Price: $2,145.67

Indicator Scores:
- RSI: 72%
- EMA Trend: 85%
- MACD: 65%
- Volume: 45%
```

---

## Next Steps

1. **Explore the UI**
   - Click countdown timer to refresh
   - Generate multiple signals
   - Copy signals to clipboard

2. **Check Backend Documentation**
   - Visit: http://localhost:8000/docs
   - View interactive API documentation

3. **Customize Settings**
   - Edit backend/config.py to add/remove pairs
   - Adjust indicator thresholds
   - Change confidence weights

4. **Read Full Documentation**
   - Open README.md for comprehensive guide
   - Review architecture and implementation

---

## Common Questions

**Q: Why is the signal for the NEXT candle?**
A: This prevents false signals on the current candle. The system calculates when the next candle opens.

**Q: Are trades executed automatically?**
A: No. This is a signal generator only. Signals are for educational analysis.

**Q: How accurate are the signals?**
A: Confidence varies. System shows indicator agreement strength. No guarantees.

**Q: Can I trade real money with this?**
A: Not recommended. System is for analysis and learning only.

**Q: How many pairs can I monitor?**
A: Default is 10 pairs. Can add more in config.py.

---

## Performance Tips

- Cache updates every 30 seconds (configurable)
- Frontend syncs time every 5 seconds
- Countdown updates every 100ms
- All operations complete in < 2 seconds

---

## Need Help?

1. Check the troubleshooting section above
2. Review backend logs in terminal
3. Check browser console (F12)
4. Verify Binance API is accessible
5. Read full README.md documentation

---

Enjoy analyzing trading signals!
