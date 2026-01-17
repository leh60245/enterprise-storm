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
import { generateReport, fetchCompanies, fetchTopics } from '../services/apiService';

const Dashboard = ({ onReportStart, onJobIdChange }) => {
  const [companies, setCompanies] = useState([]);
  const [topics, setTopics] = useState([]);
  const [selectedCompany, setSelectedCompany] = useState('');
  const [selectedTopic, setSelectedTopic] = useState('');
  const [customTopic, setCustomTopic] = useState('');
  const [loading, setLoading] = useState(false);
  const [companiesLoading, setCompaniesLoading] = useState(true);
  const [topicsLoading, setTopicsLoading] = useState(true);
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

  // 주제 목록 로드
  useEffect(() => {
    const loadTopics = async () => {
      try {
        setTopicsLoading(true);
        const data = await fetchTopics();
        setTopics(data);
        // 첫 번째 주제를 기본값으로 설정
        if (data && data.length > 0) {
          setSelectedTopic(data[0].id);
        }
        setError(null);
      } catch (err) {
        console.error('Failed to load topics:', err);
        setError('분석 주제 목록을 불러올 수 없습니다. 백엔드 서버가 실행 중인지 확인하세요.');
      } finally {
        setTopicsLoading(false);
      }
    };

    loadTopics();
  }, []);

  // 리포트 생성 핸들러
  const handleGenerate = async () => {
    if (!selectedCompany) {
      setError('기업을 선택해주세요.');
      return;
    }

    // 최종 topic 결정 (custom인 경우 customTopic 사용)
    let finalTopic = selectedTopic;
    if (selectedTopic === 'custom' || selectedTopic === 'T07') {
      if (!customTopic.trim()) {
        setError('직접 입력한 분석 주제를 입력해주세요.');
        return;
      }
      finalTopic = customTopic;
    } else {
      // 선택된 topic의 label을 가져오기
      const selectedTopicObj = topics.find(t => t.id === selectedTopic);
      if (selectedTopicObj) {
        finalTopic = selectedTopicObj.label;
      }
    }

    try {
      setLoading(true);
      setError(null);
      const response = await generateReport(selectedCompany, finalTopic);
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

  const isCustomTopic = selectedTopic === 'custom' || selectedTopic === 'T07';

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

          {/* 분석 주제 선택 */}
          <FormControl fullWidth disabled={topicsLoading}>
            <InputLabel>분석 주제</InputLabel>
            <Select
              value={selectedTopic}
              onChange={(e) => setSelectedTopic(e.target.value)}
              label="분석 주제"
            >
              {topics.map((topic) => (
                <MenuItem key={topic.id} value={topic.id}>
                  {topic.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* 직접 입력 필드 (custom 주제 선택 시에만 표시) */}
          {isCustomTopic && (
            <TextField
              label="분석 주제 직접 입력"
              value={customTopic}
              onChange={(e) => setCustomTopic(e.target.value)}
              fullWidth
              multiline
              rows={2}
              placeholder="예: 반도체 시장 분석, 글로벌 확장 전략"
            />
          )}

          {/* 선택된 주제 미리보기 */}
          {!isCustomTopic && selectedTopic && (
            <Box sx={{
              p: 2,
              backgroundColor: '#f5f5f5',
              borderRadius: '4px',
              border: '1px solid #ddd'
            }}>
              <Typography variant="caption" color="textSecondary">
                선택된 분석 주제:
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                {topics.find(t => t.id === selectedTopic)?.label || '주제 선택 대기'}
              </Typography>
            </Box>
          )}

          {/* 생성 버튼 */}
          <Button
            variant="contained"
            size="large"
            onClick={handleGenerate}
            disabled={loading || companiesLoading || topicsLoading || !selectedCompany || !selectedTopic}
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

          {(companiesLoading || topicsLoading) && (
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 2 }}>
              <CircularProgress size={20} />
              <Typography>
                {companiesLoading ? '기업 목록을 불러오는 중...' : '분석 주제를 불러오는 중...'}
              </Typography>
            </Box>
          )}
        </Box>
      </Paper>
    </Container>
  );
};

export default Dashboard;
