import React, { useState, useEffect } from 'react';
import {
  Container,
  Paper,
  Box,
  CircularProgress,
  Typography,
  Alert,
  Button,
  Chip,
  Divider,
} from '@mui/material';
import ReactMarkdown from 'react-markdown';
import { getJobStatus, getReport } from '../services/apiService';
import '../styles/ReportViewer.css';

const ReportViewer = ({ jobId, reportId, onBack }) => {
  const [status, setStatus] = useState('processing');
  const [activeReportId, setActiveReportId] = useState(reportId || null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pollingCount, setPollingCount] = useState(0);

  useEffect(() => {
    if (reportId) {
      setActiveReportId(reportId);
    }
  }, [reportId]);

  // 상태 폴링 (3초 간격)
  useEffect(() => {
    if (!jobId || activeReportId) return;

    const checkStatus = async () => {
      try {
        const statusData = await getJobStatus(jobId);
        console.log('Status:', statusData);
        setStatus(statusData.status);

        if (statusData.status === 'completed' && statusData.report_id) {
          setActiveReportId(statusData.report_id);
          setStatus(statusData.status);
        }
      } catch (err) {
        console.error('Failed to check status:', err);
        setError('상태 확인에 실패했습니다.');
      }
    };

    checkStatus();
    const interval = setInterval(() => {
      checkStatus();
      setPollingCount((c) => c + 1);
    }, 3000);

    return () => clearInterval(interval);
  }, [jobId, activeReportId]);

  // 리포트 조회 (완료 후)
  useEffect(() => {
    if (!activeReportId) return;

    const fetchReportData = async () => {
      try {
        setLoading(true);
        const reportData = await getReport(activeReportId);
        console.log('Report:', reportData);
        setReport(reportData);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch report:', err);
        setError('리포트를 불러올 수 없습니다.');
      } finally {
        setLoading(false);
      }
    };

    fetchReportData();
  }, [activeReportId]);

  // 처리 중 UI
  if (status === 'processing' && !report) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <CircularProgress size={60} />
            <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
              📋 리포트 생성 중입니다...
            </Typography>
            <Typography variant="body1" color="textSecondary">
              AI가 데이터를 분석하고 있습니다. 잠시만 기다려주세요.
            </Typography>
            <Typography variant="caption" color="textSecondary">
              (폴링: {pollingCount}회)
            </Typography>
          </Box>
        </Paper>
      </Container>
    );
  }

  // 에러 UI
  if (error) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper elevation={3} sx={{ p: 4 }}>
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
          <Button variant="contained" onClick={onBack}>
            돌아가기
          </Button>
        </Paper>
      </Container>
    );
  }

  // 로딩 중 UI
  if (loading && !report) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <CircularProgress size={50} />
            <Typography variant="body1">
              리포트를 불러오는 중...
            </Typography>
          </Box>
        </Paper>
      </Container>
    );
  }

  // 리포트 표시 UI
  if (report) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        {/* 헤더 */}
        <Paper elevation={3} sx={{ p: 3, mb: 3, backgroundColor: '#f5f5f5' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Box>
              <Typography variant="h4" sx={{ fontWeight: 'bold', mb: 1 }}>
                {report.company_name}
              </Typography>
              <Typography variant="body1" color="textSecondary">
                주제: {report.topic}
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                <Chip label={`상태: ${report.status}`} color="success" variant="outlined" />
                <Chip label={`모델: ${report.model_name}`} variant="outlined" />
                {report.created_at && (
                  <Chip
                    label={`생성: ${new Date(report.created_at).toLocaleDateString('ko-KR')}`}
                    variant="outlined"
                  />
                )}
              </Box>
            </Box>
            <Button variant="outlined" onClick={onBack}>
              ← 돌아가기
            </Button>
          </Box>
        </Paper>

        {/* 리포트 콘텐츠 */}
        <Paper elevation={2} sx={{ p: 4 }}>
          <div className="markdown-container">
            <ReactMarkdown
              components={{
                h1: ({ node, ...props }) => (
                  <Typography variant="h3" component="h1" sx={{ mt: 3, mb: 2, fontWeight: 'bold' }} {...props} />
                ),
                h2: ({ node, ...props }) => (
                  <Typography variant="h5" component="h2" sx={{ mt: 2.5, mb: 1.5, fontWeight: 'bold' }} {...props} />
                ),
                h3: ({ node, ...props }) => (
                  <Typography variant="h6" component="h3" sx={{ mt: 2, mb: 1, fontWeight: 'bold' }} {...props} />
                ),
                p: ({ node, ...props }) => (
                  <Typography variant="body1" sx={{ mb: 1.5, lineHeight: 1.7 }} {...props} />
                ),
                ul: ({ node, ...props }) => (
                  <Box component="ul" sx={{ ml: 2, mb: 1.5 }} {...props} />
                ),
                ol: ({ node, ...props }) => (
                  <Box component="ol" sx={{ ml: 2, mb: 1.5 }} {...props} />
                ),
                li: ({ node, ...props }) => (
                  <Box component="li" sx={{ mb: 0.5, lineHeight: 1.6 }} {...props} />
                ),
                table: ({ node, ...props }) => (
                  <Box sx={{
                    overflowX: 'auto',
                    mb: 2,
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                  }}>
                    <table style={{
                      width: '100%',
                      borderCollapse: 'collapse',
                      fontSize: '0.95rem',
                    }} {...props} />
                  </Box>
                ),
                thead: ({ node, ...props }) => (
                  <thead style={{ backgroundColor: '#f0f0f0' }} {...props} />
                ),
                th: ({ node, ...props }) => (
                  <th style={{
                    padding: '12px',
                    textAlign: 'left',
                    borderBottom: '2px solid #ddd',
                    fontWeight: 'bold',
                  }} {...props} />
                ),
                td: ({ node, ...props }) => (
                  <td style={{
                    padding: '10px 12px',
                    borderBottom: '1px solid #eee',
                  }} {...props} />
                ),
                code: ({ node, inline, ...props }) => (
                  inline ? (
                    <code style={{
                      backgroundColor: '#f5f5f5',
                      padding: '2px 6px',
                      borderRadius: '3px',
                      fontFamily: 'monospace',
                    }} {...props} />
                  ) : (
                    <pre style={{
                      backgroundColor: '#f5f5f5',
                      padding: '12px',
                      borderRadius: '4px',
                      overflowX: 'auto',
                      mb: '1.5rem',
                    }}>
                      <code {...props} />
                    </pre>
                  )
                ),
                blockquote: ({ node, ...props }) => (
                  <Box
                    component="blockquote"
                    sx={{
                      borderLeft: '4px solid #1976d2',
                      paddingLeft: 2,
                      marginLeft: 0,
                      marginY: 2,
                      fontStyle: 'italic',
                      color: 'textSecondary',
                    }}
                    {...props}
                  />
                ),
                a: ({ node, ...props }) => (
                  <Typography
                    component="a"
                    sx={{
                      color: '#1976d2',
                      textDecoration: 'none',
                      '&:hover': { textDecoration: 'underline' },
                    }}
                    {...props}
                  />
                ),
              }}
            >
              {report.report_content}
            </ReactMarkdown>
          </div>

          {/* 목차 (있으면 표시) */}
          {report.toc_text && (
            <>
              <Divider sx={{ my: 3 }} />
              <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2 }}>
                📑 목차
              </Typography>
              <Typography variant="body2" component="pre" sx={{
                backgroundColor: '#f5f5f5',
                p: 2,
                borderRadius: '4px',
                overflow: 'auto',
              }}>
                {report.toc_text}
              </Typography>
            </>
          )}

          {/* 메타정보 (있으면 표시) */}
          {/* {report.meta_info && (
            <>
              <Divider sx={{ my: 3 }} />
              <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2 }}>
                ℹ️ 생성 정보
              </Typography>
              <Typography component="pre" variant="body2" sx={{
                backgroundColor: '#f5f5f5',
                p: 2,
                borderRadius: '4px',
                overflow: 'auto',
                fontSize: '0.85rem',
              }}>
                {JSON.stringify(report.meta_info, null, 2)}
              </Typography>
            </>
          )} */}

          {/* 참고 문헌 (url_to_info 형식) */}
          {report.references && typeof report.references === 'object' && report.references.url_to_info && (
            <>
              <Divider sx={{ my: 3 }} />
              <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2 }}>
                📚 참고 문헌
              </Typography>
              <Box component="ul" sx={{ pl: 2, m: 0 }}>
                {Object.entries(report.references.url_to_info).map(([url, info], idx) => (
                  <Box key={`${url}-${idx}`} component="li" sx={{ mb: 1.5 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                      {info.title || url}
                    </Typography>
                    {info.snippet && (
                      <Typography variant="body2" sx={{ mt: 0.5, color: 'text.secondary' }}>
                        {info.snippet}
                      </Typography>
                    )}
                    {url && (
                      <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: 0.5 }}>
                        URL: {url}
                      </Typography>
                    )}
                  </Box>
                ))}
              </Box>
            </>
          )}
        </Paper>

        {/* 하단 액션 */}
        <Box sx={{ mt: 4, display: 'flex', gap: 2, justifyContent: 'center' }}>
          <Button variant="contained" onClick={onBack}>
            ← 새로운 리포트 생성
          </Button>
          <Button variant="outlined">
            📥 다운로드
          </Button>
        </Box>
      </Container>
    );
  }

  return null;
};

export default ReportViewer;
