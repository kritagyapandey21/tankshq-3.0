# START HERE - Quick Setup Checklist

## Before You Start
- [ ] Python 3.8+ installed (`python --version`)
- [ ] Project extracted to desktop or documents
- [ ] Administrator/sudo access (if needed)

---

## Step 1: Start Backend (Terminal/Command Prompt 1)

### Windows Users
```bash
cd "C:\Users\YourName\OneDrive\Desktop\Tan new\trading-signal-system"
run_backend.bat
```

### macOS/Linux Users
```bash
cd ~/Desktop/trading-signal-system
bash run_backend.sh
```

### What to See
```
2024-06-05 14:00:00 - Started server process
INFO: Uvicorn running on http://0.0.0.0:8000
```

**✓ Leave this window open**

---

## Step 2: Start Frontend (Terminal/Command Prompt 2)

### Windows Users
```bash
cd "C:\Users\YourName\OneDrive\Desktop\Tan new\trading-signal-system"
run_frontend.bat
```

### macOS/Linux Users
```bash
cd ~/Desktop/trading-signal-system
bash run_frontend.sh
```

### What to See
```
Serving HTTP on 0.0.0.0 port 3000
```

**✓ Leave this window open**

---

## Step 3: Open in Browser

Click or navigate to:
```
http://localhost:3000
```

### What You Should See
- Professional trading interface
- Green "Connected" status dot
- "Get Best Signal" button (enabled)
- Server time displaying

---

## Step 4: Generate First Signal

1. Click **"Get Best Signal"** button
2. Wait 1-2 seconds for analysis
3. Signal appears with:
   - Trading pair (e.g., ETHUSDT)
   - Direction (CALL or PUT)
   - Confidence percentage
   - Entry & expiry times
   - Indicator scores
   - Countdown timer

---

## Troubleshooting

### Backend Won't Start
```
Error: ModuleNotFoundError: No module named 'fastapi'
```
**Solution**: Install dependencies
```bash
cd backend
python -m pip install -r requirements.txt
```

### Frontend Can't Connect
```
Console Error: Failed to fetch http://localhost:8000/signal
```
**Solution**:
1. Verify backend is running (check other terminal)
2. Verify http://localhost:8000/health works
3. Check CORS not blocked (should say "Connected")

### Port Already in Use
```
Error: Address already in use
```
**Solution**: Kill the process or use different port
```bash
# Windows: Find and kill
netstat -ano | findstr :8000
taskkill /PID <number> /F

# macOS/Linux: Find and kill
lsof -i :8000
kill -9 <number>
```

---

## Verification

Run these tests in a new terminal:

```bash
# Test Backend
curl http://localhost:8000/health
# Expected: {"status":"healthy",...}

# Test API
curl http://localhost:8000/signal
# Expected: {"pair":"...","direction":"CALL",...}

# Test Server Time
curl http://localhost:8000/server-time
# Expected: {"server_time":"HH:MM:SS",...}
```

---

## Common Questions

**Q: Why signals for next candle?**
A: Prevents false signals on current candle, ensures accurate entry timing

**Q: Do trades execute automatically?**
A: No. This is signal generation only for analysis

**Q: How accurate are signals?**
A: Confidence varies. System shows indicator agreement strength

**Q: Can I customize pairs?**
A: Yes. Edit `backend/config.py`, change `TRADING_PAIRS` list

**Q: Where are signals stored?**
A: Not stored by default. Add database for history

---

## Next Steps

### Explore UI
- [ ] Click "Get Best Signal" multiple times
- [ ] Watch countdown timer
- [ ] Copy signal to clipboard
- [ ] Generate new signal

### Learn System
- [ ] Read README.md (full documentation)
- [ ] Review TECHNICAL.md (developer guide)
- [ ] Check backend logs for details
- [ ] Test API endpoints manually

### Customize
- [ ] Edit trading pairs in config.py
- [ ] Adjust indicator weights
- [ ] Change cache duration
- [ ] Add new trading pairs

### Extend
- [ ] Add database for history
- [ ] Create WebSocket updates
- [ ] Build accuracy dashboard
- [ ] Add email alerts

---

## File Locations

```
Project Root:
├── README.md              ← Full documentation
├── QUICKSTART.md          ← 5-minute guide
├── INSTALLATION.md        ← Detailed setup
├── TECHNICAL.md           ← Developer guide
├── PROJECT_SUMMARY.md     ← Overview
├── START_HERE.md          ← This file
│
├── backend/
│   ├── app.py            ← Main API
│   ├── config.py         ← Edit to customize
│   ├── market_data.py
│   ├── indicators.py
│   ├── analysis.py
│   └── requirements.txt
│
└── frontend/
    ├── index.html        ← UI
    ├── styles.css        ← Styling
    └── app.js           ← Logic
```

---

## Desktop Shortcuts (Windows)

Right-click desktop → New → Shortcut

**Backend Shortcut Target:**
```
cmd.exe /K "cd C:\Users\YourName\OneDrive\Desktop\Tan new\trading-signal-system && run_backend.bat"
```

**Frontend Shortcut Target:**
```
cmd.exe /K "cd C:\Users\YourName\OneDrive\Desktop\Tan new\trading-signal-system && run_frontend.bat"
```

---

## System Requirements

Minimum:
- Python 3.8+
- 512 MB RAM
- 100 MB disk
- Internet

---

## API Documentation

Once running, visit:
```
http://localhost:8000/docs
```

Interactive Swagger documentation with all endpoints

---

## Stopping the System

### Backend Terminal
Press: `Ctrl+C`

### Frontend Terminal
Press: `Ctrl+C`

Both windows will close

---

## Starting Again

Just repeat:
1. `run_backend.bat` (or .sh)
2. `run_frontend.bat` (or .sh)
3. Open http://localhost:3000

---

## Performance Expectations

✓ Signal generation: 1-2 seconds
✓ UI display: Instant
✓ Countdown update: Smooth (100ms)
✓ Time sync: Accurate (every 5s)

---

## Success Indicators

- [ ] Green connected status dot
- [ ] "Get Best Signal" button works
- [ ] Signal displays in < 2 seconds
- [ ] Countdown timer counting down
- [ ] All indicator scores showing
- [ ] Copy button works
- [ ] No errors in console (F12)

---

## Pro Tips

1. **Multiple Signals**: Click button again for different pair
2. **Indicator Analysis**: Watch how scores change
3. **Confidence**: Higher % = stronger signal
4. **Timing**: Entry time shows when signal becomes valid
5. **Copy**: Use for backtesting or tracking

---

## Emergency Help

### Complete Reset
```bash
# Stop both terminals (Ctrl+C)
cd backend
rm -r venv
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Check All Services
```bash
# Backend health
curl http://localhost:8000/health

# Frontend load
Open http://localhost:3000 in browser

# API working
curl http://localhost:8000/signal
```

---

## Remember

✅ Signals are for ANALYSIS and EDUCATION
✅ No trades execute automatically
✅ Always use risk management
✅ Never risk money you can't afford to lose
✅ Consult financial advisors for real trading

---

## You're All Set!

Your trading signal system is ready to use.

**Start with:**
```
http://localhost:3000
```

**Click:** "Get Best Signal"

**Enjoy!** 📊

---

For detailed information:
- Full Guide: README.md
- Quick Setup: QUICKSTART.md  
- Installation: INSTALLATION.md
- Technical: TECHNICAL.md

Questions? Check those documents or the troubleshooting section above.
