import axios from 'axios';

// Parse and handle API base URL without the trailing `/api` segment
let baseURL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
// Remove trailing `/api` if present to avoid path doubling
const API_BASE_URL = baseURL.endsWith('/api') ? baseURL : `${baseURL}/api`;

// Create axios instance with base URL
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: false, // Set to false for CORS requests with credentials
});

// Add auth token to requests if available
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Error handling interceptor
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);

// API endpoints
const apiService = {
  // Authentication
  login: (username, password) => {
    return apiClient.post('/auth/token', { username, password });
  },
  getCurrentUser: () => apiClient.get('/auth/users/me'),
  
  // Dashboard & Statistics
  getArticleStats: () => apiClient.get('/stats/articles'),
  getSourceStats: () => apiClient.get('/stats/sources'),
  getArticlesOverTime: () => apiClient.get('/articles/over-time'),
  
  // Articles
  getTrendingArticles: (days = 7, limit = 10) => 
    apiClient.get(`/trending?days=${days}&limit=${limit}`),
  getSimilarArticles: (articleId, limit = 5) => 
    apiClient.get(`/articles/similar/${articleId}?limit=${limit}`),
  
  // Search
  searchArticles: (query, limit = 20) => 
    apiClient.get(`/search?query=${encodeURIComponent(query)}&limit=${limit}`),
  
  // Sources
  getAllSources: () => apiClient.get('/sources'),
  addSource: (name, url, sourceType = 'rss', active = true) => 
    apiClient.post('/sources', { name, url, source_type: sourceType, active }),
  updateSource: (sourceId, name, url, sourceType, active) => 
    apiClient.put(`/sources/${sourceId}`, { name, url, source_type: sourceType, active }),
  deleteSource: (sourceId) => 
    apiClient.delete(`/sources/${sourceId}`),
};

export default apiService;
