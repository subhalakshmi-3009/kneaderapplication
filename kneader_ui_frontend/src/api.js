import axios from 'axios';

const API_BASE_URL = 'http://127.0.0.1:5000/api'; // or remove /api if not used

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
});

// === Automatically attach JWT token ===
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// === Handle token expiry ===
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      console.warn('Token expired or invalid — logging out');
      localStorage.removeItem('token');
      window.location.reload();
    }
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

// === AUTH ===
export const login = async (username, password) => {
  const res = await api.post('/login', { username, password });
  const token = res.data.token || res.data.access_token;
  if (token) localStorage.setItem('token', token);
  return res.data;
};

export const getStatus = () => api.get('/status').then(r => r.data);
export const scanItem = (barcode) => api.post('/scan', { barcode }).then(r => r.data);
export const abortProcess = () => api.post('/abort').then(r => r.data);
export const resumeProcess = () => api.post('/resume').then(r => r.data);

export const completeAbortProcess = () =>
  api.post('/complete_abort')
    .then(r => r.data)
    .catch(() => ({ status: 'error', message: 'API call failed' }));

export const cancelProcess = () =>
  api.post('/cancel')
    .then(r => r.data)
    .catch(() => ({ status: 'error', message: 'Cancel API call failed' }));

export const resetProcess = () => api.post('/reset').then(r => r.data);
export const getWorkorders = () => api.get('/workorders').then(r => r.data);
export const checkTransitions = () => api.get('/check_transitions').then(r => r.data);

export const getBatches = (batchNumber = '') => {
  const url = batchNumber ? `/batches/${batchNumber}` : '/batches';
  return api.get(url).then(r => r.data);
};

export const loadWorkorder = ({ batchNumber, batchType }) =>
  api.post('/load_workorder', { batchNumber, batchType })
    .then(r => r.data)
    .catch(() => ({ status: 'error', message: 'Failed to load workorder' }));

export const confirmCompletion = () =>
  api.post('/confirm_completion')
    .then(r => r.data)
    .catch(() => ({ status: 'error', message: 'Failed to confirm completion' }));

export const prescanItem = (barcode) => api.post('/prescan', { barcode }).then(r => r.data);

export const saveWorkorder = () =>
  api.post('/save_workorder')
    .then(r => r.data)
    .catch(() => ({ status: 'error', message: 'Failed to save workorder' }));

export const confirmPrescanAPI = () => api.post('/confirm_prescan').then(r => r.data);

export default api;
