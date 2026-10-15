#!/bin/bash
# Trading Signal System - Frontend Startup Script for macOS/Linux

echo ""
echo "========================================"
echo "Trading Signal System - Frontend Server"
echo "========================================"
echo ""

cd frontend

echo ""
echo "========================================"
echo "Starting Frontend Server..."
echo "========================================"
echo "Frontend will start on http://localhost:3000"
echo ""
echo "Make sure the backend is running on http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

python3 -m http.server 3000
