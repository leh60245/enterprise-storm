/**
 * API Service Layer
 * Communicates with Backend API (localhost:8000)
 */

import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * 분석 주제(Topics) 목록 조회
 * GET /api/topics
 */
export const fetchTopics = async () => {
  try {
    const response = await apiClient.get('/api/topics');
    return response.data;
  } catch (error) {
    console.error('Failed to fetch topics:', error);
    throw error;
  }
};

/**
 * 기업 목록 조회
 * GET /api/companies
 */
export const fetchCompanies = async () => {
  try {
    const response = await apiClient.get('/api/companies');
    return response.data;
  } catch (error) {
    console.error('Failed to fetch companies:', error);
    throw error;
  }
};

/**
 * 리포트 생성 요청
 * POST /api/generate
 */
export const generateReport = async (companyName, topic) => {
  try {
    const response = await apiClient.post('/api/generate', {
      company_name: companyName,
      topic: topic,
    });
    return response.data;
  } catch (error) {
    console.error('Failed to generate report:', error);
    throw error;
  }
};

/**
 * 작업 상태 조회
 * GET /api/status/{job_id}
 */
export const getJobStatus = async (jobId) => {
  try {
    const response = await apiClient.get(`/api/status/${jobId}`);
    return response.data;
  } catch (error) {
    console.error(`Failed to get job status for ${jobId}:`, error);
    throw error;
  }
};

/**
 * 리포트 조회
 * GET /api/report/{id}
 */
export const getReport = async (reportId) => {
  try {
    const response = await apiClient.get(`/api/report/${reportId}`);
    return response.data;
  } catch (error) {
    console.error(`Failed to get report ${reportId}:`, error);
    throw error;
  }
};

/**
 * Health Check
 * GET /
 */
export const healthCheck = async () => {
  try {
    const response = await apiClient.get('/');
    return response.data;
  } catch (error) {
    console.error('Health check failed:', error);
    throw error;
  }
};

export default apiClient;
