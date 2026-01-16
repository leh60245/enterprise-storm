import React, { useState, useEffect } from 'react';
import {
  Container,
  Paper,
  Box,
  TextField,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  CircularProgress,
  Typography,
  Alert,
} from '@mui/material';
import { generateReport, fetchCompanies } from '../services/apiService';

const Dashboard = ({ onReportStart, onJobIdChange }) => {
  const [companies, setCompanies] = useState([]);
  const [selectedCompany, setSelectedCompany] = useState('');
  const [topic, setTopic] = useState('종합 분석');
  const [loading, setLoading] = useState(false);
  const [companiesLoading, setCompaniesLoading] = useState(true);
  const [error, setError] = useState(null);

  // 기업 목록 로드
  useEffect(() => {
    const loadCompanies = async () => {
      try {
        setCompaniesLoading(true);
        const data = await fetchCompanies();
        setCompanies(data);
        setError(null);
      } catch (err) {
        console.error('Failed to load companies:', err);
        setError('기업 목록을 불러올 수 없습니다. 백엔드 서버가 실행 중인지 확인하세요.');
        // Fallback 데이터
        setCompanies(['SK하이닉스', '현대엔지니어링', 'NAVER', '삼성전자']);
      } finally {
        setCompaniesLoading(false);
      }
    };

    loadCompanies();
  }, []);

  // 리포트 생성 핸들러
  const handleGenerate = async () => {
    if (!selectedCompany || !topic) {
      setError('기업과 주제를 모두 선택해주세요.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const response = await generateReport(selectedCompany, topic);
      console.log('Generate response:', response);

      // JobID를 부모로 전달
      onJobIdChange(response.job_id);
      onReportStart(response.job_id);
    } catch (err) {
      console.error('Failed to generate report:', err);
      setError('리포트 생성 요청에 실패했습니다. 다시 시도해주세요.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Paper elevation={3} sx={{ p: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom sx={{ mb: 3, fontWeight: 'bold' }}>
          📊 Enterprise STORM Report Generator
        </Typography>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {/* 기업 선택 */}
          <FormControl fullWidth disabled={companiesLoading}>
            <InputLabel>기업 선택</InputLabel>
            <Select
              value={selectedCompany}
              onChange={(e) => setSelectedCompany(e.target.value)}
              label="기업 선택"
            >
              {companies.map((company) => (
                <MenuItem key={company} value={company}>
                  {company}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* 주제 입력 */}
          <TextField
            label="분석 주제"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            fullWidth
            multiline
            rows={2}
            placeholder="예: 재무 분석, 성장 전망, 시장 경쟁력 분석"
          />

          {/* 생성 버튼 */}
          <Button
            variant="contained"
            size="large"
            onClick={handleGenerate}
            disabled={loading || companiesLoading || !selectedCompany}
            sx={{
              py: 1.5,
              backgroundColor: '#1976d2',
              '&:hover': { backgroundColor: '#1565c0' },
              fontSize: '1.1rem',
            }}
          >
            {loading ? (
              <>
                <CircularProgress size={24} sx={{ mr: 2, color: 'white' }} />
                생성 중...
              </>
            ) : (
              '📄 리포트 생성'
            )}
          </Button>

          {companiesLoading && (
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 2 }}>
              <CircularProgress size={20} />
              <Typography>기업 목록을 불러오는 중...</Typography>
            </Box>
          )}
        </Box>
      </Paper>
    </Container>
  );
};

export default Dashboard;
