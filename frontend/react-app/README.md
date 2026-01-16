# Enterprise STORM Frontend (React)

React 기반 프론트엔드 애플리케이션으로 백엔드 API (localhost:8000)와 연동됩니다.

## 설치 및 실행

### 1. 의존성 설치
```bash
cd frontend/react-app
npm install
```

### 2. 개발 서버 실행 (localhost:3000)
```bash
npm run dev
```

### 3. 프로덕션 빌드
```bash
npm run build
```

## 주요 기능

- ✅ 실시간 기업 목록 조회 (GET /api/companies)
- ✅ 리포트 생성 요청 (POST /api/generate)
- ✅ 상태 폴링 (3초 간격, GET /api/status/{jobId})
- ✅ Markdown 렌더링 (테이블, 코드블록 포함)

## 기술 스택

- React 18 + Vite
- Material-UI (MUI) 5
- axios (HTTP 클라이언트)
- react-markdown (Markdown 렌더링)

## 백엔드 연동

백엔드 API는 `http://localhost:8000`에서 실행되어야 합니다.

```bash
# 백엔드 실행 (프로젝트 루트)
python -m uvicorn backend.main:app --reload --port 8000
```

## 개발

### 컴포넌트 추가
- Dashboard: 기업 선택 및 생성 요청
- ReportViewer: Markdown 리포트 렌더링

