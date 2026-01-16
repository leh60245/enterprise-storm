#!/bin/bash
# Frontend Integration Test Script
# 백엔드 테스트 데이터 생성 및 서버 시작

echo "=================================================="
echo "Enterprise STORM Frontend Integration Test"
echo "=================================================="
echo ""

echo "[1/3] Generating test data..."
cd "$(dirname "$0")"
python -m backend.generate_test_data

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Test data generated successfully!"
    echo ""
    echo "[2/3] Starting backend server..."
    echo "      API Base: http://localhost:8000"
    echo "      Frontend: http://localhost:3000 (start separately)"
    echo ""
    echo "      Press Ctrl+C to stop"
    echo ""
    python -m uvicorn backend.main:app --reload --port 8000
else
    echo ""
    echo "❌ Failed to generate test data"
    exit 1
fi
