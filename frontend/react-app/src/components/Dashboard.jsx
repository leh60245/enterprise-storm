import React, { useState, useEffect } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import {
  fetchCompanies,
  fetchTopics,
  fetchReports,
  generateReport,
} from '../services/apiService';

const Dashboard = ({ onReportStart, onJobIdChange, onViewReport }) => {
  const [companies, setCompanies] = useState([]);
  const [topics, setTopics] = useState([]);
  const [reports, setReports] = useState([]);
  const [reportsTotal, setReportsTotal] = useState(0);
  const [filters, setFilters] = useState({ company: '', topic: '' });
  const [reportsLoading, setReportsLoading] = useState(false);
  const [metaLoading, setMetaLoading] = useState(true);
  const [error, setError] = useState(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [modalCompany, setModalCompany] = useState('');
  const [modalTopic, setModalTopic] = useState('');
  const [modalCustomTopic, setModalCustomTopic] = useState('');
  const [creating, setCreating] = useState(false);

  const isCustomTopic = modalTopic === 'custom';

  const loadReferenceData = async () => {
    try {
      setMetaLoading(true);
      const [companiesData, topicsData] = await Promise.all([
        fetchCompanies(),
        fetchTopics(),
      ]);
      setCompanies(companiesData || []);
      setTopics(topicsData || []);
      if (companiesData?.length) {
        setModalCompany(companiesData[0]);
      }
      if (topicsData?.length) {
        setModalTopic(topicsData[0].id);
      }
      setError(null);
    } catch (err) {
      console.error('Failed to load reference data:', err);
      setError('기준 데이터를 불러올 수 없습니다. 서버 상태를 확인하세요.');
    } finally {
      setMetaLoading(false);
    }
  };

  const loadReports = async () => {
    try {
      setReportsLoading(true);
      const params = {
        company_name: filters.company || undefined,
        topic: filters.topic || undefined,
        sort_by: 'created_at',
        order: 'desc',
        limit: 50,
        offset: 0,
      };
      const data = await fetchReports(params);
      setReports(data?.reports || []);
      setReportsTotal(data?.total || 0);
      setError(null);
    } catch (err) {
      console.error('Failed to load reports:', err);
      setError('리포트 목록을 불러올 수 없습니다.');
    } finally {
      setReportsLoading(false);
    }
  };

  useEffect(() => {
    loadReferenceData();
  }, []);

  useEffect(() => {
    loadReports();
  }, [filters.company, filters.topic]);

  const openCreateModal = () => {
    setCreateOpen(true);
    setModalCustomTopic('');
    if (topics?.length && !modalTopic) {
      setModalTopic(topics[0].id);
    }
    if (companies?.length && !modalCompany) {
      setModalCompany(companies[0]);
    }
  };

  const closeCreateModal = () => {
    setCreateOpen(false);
    setCreating(false);
  };

  const handleGenerate = async () => {
    if (!modalCompany || !modalTopic) {
      setError('기업과 주제를 모두 선택해주세요.');
      return;
    }

    let finalTopic = modalTopic;
    if (isCustomTopic) {
      if (!modalCustomTopic.trim()) {
        setError('직접 입력한 분석 주제를 입력해주세요.');
        return;
      }
      finalTopic = modalCustomTopic.trim();
    } else {
      const selected = topics.find((t) => t.id === modalTopic);
      finalTopic = selected?.label || finalTopic;
    }

    try {
      setCreating(true);
      const response = await generateReport(modalCompany, finalTopic);
      const optimisticRow = {
        report_id: response?.report_id || null,
        company_name: modalCompany,
        topic: finalTopic,
        model_name: response?.model_name || 'pending',
        created_at: new Date().toISOString(),
        status: 'processing',
        job_id: response?.job_id,
      };
      setReports((prev) => [optimisticRow, ...prev]);
      setReportsTotal((prev) => prev + 1);

      if (response?.job_id) {
        onJobIdChange(response.job_id);
        onReportStart(response.job_id);
      }

      closeCreateModal();
      setError(null);
    } catch (err) {
      console.error('Failed to generate report:', err);
      setError('리포트 생성 요청에 실패했습니다. 다시 시도해주세요.');
    } finally {
      setCreating(false);
    }
  };

  const renderStatusChip = (status) => {
    const colorMap = {
      completed: 'success',
      processing: 'warning',
      failed: 'error',
    };
    return (
      <Chip
        size="small"
        color={colorMap[status] || 'default'}
        label={status || 'unknown'}
      />
    );
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Paper elevation={3} sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
              📊 Enterprise STORM Dashboard
            </Typography>
            <Typography variant="body2" color="textSecondary">
              생성된 리포트를 테이블로 관리하고 새 리포트를 생성하세요.
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button
              startIcon={<RefreshIcon />}
              variant="outlined"
              onClick={loadReports}
              disabled={reportsLoading}
            >
              새로고침
            </Button>
            <Button
              startIcon={<AddIcon />}
              variant="contained"
              onClick={openCreateModal}
              disabled={metaLoading}
            >
              새 리포트 생성
            </Button>
          </Stack>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
          <FormControl sx={{ minWidth: 200 }} size="small">
            <InputLabel>기업 필터</InputLabel>
            <Select
              label="기업 필터"
              value={filters.company}
              onChange={(e) => setFilters((f) => ({ ...f, company: e.target.value }))}
            >
              <MenuItem value="">전체</MenuItem>
              {companies.map((company) => (
                <MenuItem key={company} value={company}>
                  {company}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl sx={{ minWidth: 220 }} size="small">
            <InputLabel>주제 필터</InputLabel>
            <Select
              label="주제 필터"
              value={filters.topic}
              onChange={(e) => setFilters((f) => ({ ...f, topic: e.target.value }))}
            >
              <MenuItem value="">전체</MenuItem>
              {topics.map((topic) => (
                <MenuItem key={topic.id} value={topic.label}>
                  {topic.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        <Paper variant="outlined" sx={{ width: '100%', overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>기업명</TableCell>
                <TableCell>분석 주제</TableCell>
                <TableCell>모델</TableCell>
                <TableCell>생성 일시</TableCell>
                <TableCell>상태</TableCell>
                <TableCell align="right">Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {reportsLoading ? (
                <TableRow>
                  <TableCell colSpan={7} align="center">
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}>
                      <CircularProgress size={20} />
                      <Typography variant="body2">리포트를 불러오는 중...</Typography>
                    </Box>
                  </TableCell>
                </TableRow>
              ) : reports.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} align="center">
                    <Typography variant="body2">표시할 리포트가 없습니다.</Typography>
                  </TableCell>
                </TableRow>
              ) : (
                reports.map((row) => (
                  <TableRow key={`${row.report_id || 'pending'}-${row.company_name}-${row.topic}`} hover>
                    <TableCell>{row.report_id || '—'}</TableCell>
                    <TableCell>{row.company_name}</TableCell>
                    <TableCell>{row.topic}</TableCell>
                    <TableCell>{row.model_name || '—'}</TableCell>
                    <TableCell>
                      {row.created_at
                        ? new Date(row.created_at).toLocaleString('ko-KR')
                        : '—'}
                    </TableCell>
                    <TableCell>{renderStatusChip(row.status)}</TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={!row.report_id}
                        onClick={() => onViewReport && onViewReport(row.report_id)}
                      >
                        보기
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Paper>

        <Typography variant="caption" sx={{ mt: 1, display: 'block' }}>
          총 {reportsTotal}건
        </Typography>
      </Paper>

      {/* 생성 모달 */}
      <Dialog open={createOpen} onClose={closeCreateModal} fullWidth maxWidth="sm">
        <DialogTitle>새 리포트 생성</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
          <FormControl fullWidth disabled={metaLoading}>
            <InputLabel>기업 선택</InputLabel>
            <Select
              label="기업 선택"
              value={modalCompany}
              onChange={(e) => setModalCompany(e.target.value)}
            >
              {companies.map((company) => (
                <MenuItem key={company} value={company}>
                  {company}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth disabled={metaLoading}>
            <InputLabel>분석 주제</InputLabel>
            <Select
              label="분석 주제"
              value={modalTopic}
              onChange={(e) => setModalTopic(e.target.value)}
            >
              {topics.map((topic) => (
                <MenuItem key={topic.id} value={topic.id}>
                  {topic.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {isCustomTopic && (
            <TextField
              label="분석 주제 직접 입력"
              value={modalCustomTopic}
              onChange={(e) => setModalCustomTopic(e.target.value)}
              fullWidth
              multiline
              rows={2}
              placeholder="예: 재무 분석, 글로벌 확장 전략"
            />
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={closeCreateModal} disabled={creating}>취소</Button>
          <Button
            variant="contained"
            onClick={handleGenerate}
            disabled={creating || !modalCompany || !modalTopic}
          >
            {creating ? <CircularProgress size={20} sx={{ color: 'white' }} /> : '생성'}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default Dashboard;
