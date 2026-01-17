import React, { useState } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { Box } from '@mui/material';
import Dashboard from './components/Dashboard';
import ReportViewer from './components/ReportViewer';

// MUI 테마 설정 (1920x1080 해상도 기준)
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
      paper: '#ffffff',
    },
  },
  typography: {
    fontFamily: [
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif',
    ].join(','),
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontSize: '1rem',
        },
      },
    },
  },
});

/**
 * Enterprise STORM Frontend Application
 *
 * Architecture:
 * - Dashboard: 기업 선택 및 리포트 생성 요청
 * - ReportViewer: 생성된 리포트 표시 (Markdown 렌더링)
 * - Global State: jobId를 통한 상태 관리
 *
 * Flow:
 * 1. Dashboard에서 기업 선택 → 생성 요청 (POST /api/generate)
 * 2. jobId 획득 → ReportViewer로 전환
 * 3. ReportViewer에서 3초 간격 폴링 (GET /api/status/{jobId})
 * 4. status=completed → reportId 추출
 * 5. reportId로 리포트 조회 (GET /api/report/{reportId})
 * 6. react-markdown으로 렌더링
 */

function App() {
  const [view, setView] = useState('dashboard'); // 'dashboard' | 'viewer'
  const [jobId, setJobId] = useState(null);
  const [reportId, setReportId] = useState(null);

  const handleReportStart = (newJobId) => {
    setJobId(newJobId);
    setReportId(null);
    setView('viewer');
  };

  const handleViewReport = (id) => {
    setReportId(id);
    setJobId(null);
    setView('viewer');
  };

  const handleBackToDashboard = () => {
    setView('dashboard');
    setJobId(null);
    setReportId(null);
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box
        sx={{
          width: '100%',
          minHeight: '100vh',
          backgroundColor: '#f5f5f5',
        }}
      >
        {view === 'dashboard' ? (
          <Dashboard
            onReportStart={handleReportStart}
            onJobIdChange={setJobId}
            onViewReport={handleViewReport}
          />
        ) : (
          <ReportViewer
            jobId={jobId}
            reportId={reportId}
            onBack={handleBackToDashboard}
          />
        )}
      </Box>
    </ThemeProvider>
  );
}

export default App;
