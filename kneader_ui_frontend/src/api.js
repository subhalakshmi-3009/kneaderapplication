import axios from 'axios';

//const API_BASE_URL = 'https://shera-undefensible-pseudoindependently.ngrok-free.dev';
const API_BASE_URL ="http://127.0.0.1:5000";

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  timeout: 90000,
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
  const res = await api.post('/api/login', {
    usr: username,
    pwd: password
  })
  return res.data
}

export const getStatus = () => api.get('/api/status').then(r => r.data);
export const scanItem = (barcode) => api.post('/api/scan', { barcode }).then(r => r.data);
export const abortProcess = () => api.post('/api/abort').then(r => r.data);
export const resumeProcess = () => api.post('/api/resume').then(r => r.data);

export const completeAbortProcess = () =>
  api.post('/api/complete_abort')
    .then(r => r.data)
    .catch(() => ({ status: 'error', message: 'API call failed' }));

export const cancelProcess = () =>
  api.post('/api/cancel')
    .then(r => r.data)
    .catch(() => ({ status: 'error', message: 'Cancel API call failed' }));

export const resetProcess = () => api.post('/api/reset').then(r => r.data);
export const getWorkorders = () => api.get('/api/workorders').then(r => r.data);
export const checkTransitions = () => api.get('/api/check_transitions').then(r => r.data);

export const getBatches = (batchNumber = '') => {
  const url = batchNumber ? `/api/batches/${batchNumber}` : '/batches';
  return api.get(url).then(r => r.data);
};

// updated: call the working endpoint and return .data
export const loadWorkorder = ({ batch_no }) =>
  api.post('/api/load_workorder', { batch_no })
     .then(r => r.data)
     .catch(err => { throw err })

     export async function getPrescanState(sessionId) {
  const res = await api.get('/api/prescan_state', {
    params: { session_id: sessionId }
  });
  return res.data;
}



export const confirmCompletion = () =>
  api.post('/api/confirm_completion')
    .then(r => r.data)
    .catch(() => ({ status: 'error', message: 'Failed to confirm completion' }));

// api.js

export const prescanItem = (barcode, sessionId) => {
  return api.post('/api/prescan', {
    barcode,
    session_id: sessionId
  }).then(r => r.data);
};


export const saveWorkorder = () =>
  api.post('/api/save_workorder')
    .then(r => r.data)
    .catch(() => ({ status: 'error', message: 'Failed to save workorder' }));

export const confirmPrescanAPI = () => api.post('/api/confirm_prescan').then(r => r.data);
// === ERPNext Integration ===
export const getERPWorkorders = () =>
  api.get('/api/erp/workorders').then(r => r.data);

export const getERPBOM = (bomName) =>
  api.get(`/api/erp/bom/${bomName}`).then(r => r.data);

export const updateERPWorkorder = (workOrder, status = 'Completed', actualQty = 0) =>
  api.post('/api/erp/update_workorder', { work_order: workOrder, status, actual_qty: actualQty })
     .then(r => r.data);

export const createERPBatch = (batchId, item, manufacturingDate) =>
  api.post('/api/erp/create_batch', { batch_id: batchId, item, manufacturing_date: manufacturingDate })
     .then(r => r.data);


export default api;
