import axios from 'axios'

// Direct connection to Flask on port 5000
const API_BASE_URL = 'http://127.0.0.1:5000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000
})

// Add response interceptor to handle errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error)
    throw error
  }
)

export const getStatus = () => {
  return api.get('/status').then(response => response.data)
}

export const scanItem = (barcode) => {
  return api.post('/scan', { barcode }).then(response => response.data)
}

export const abortProcess = () => {
  return api.post('/control/abort').then(response => response.data)
}

export const resumeProcess = () => {
  return api.post('/control/resume').then(response => response.data)
}


export const resetController = () => {
  return api.post('/control/reset').then(response => response.data)
}

export const getWorkorders = () => {
  return api.get('/workorders').then(response => response.data)
}

export const checkTransitions = () => {
  return api.get('/check_transitions').then(response => response.data)
}
// Add these to your api.js file
export const getBatches = () => {
  return api.get('/batches/:batch_number').then(response => response.data);
};

export const loadWorkorder = (batch_number) => {
  alert("posting")
  return api.post('/load_workorder', { 'batchNumber': batch_number })
    .then(response => response.data)
    .catch(error => {
      console.error('API Error loading workorder:', error);

      return { status: 'error', message: 'Failed to load workorder' };
    });
};
export const prescanItem = (barcode) => {
  return api.post('/prescan', { 'barcode':barcode }).then(response => response.data);
};

export const confirmPrescanAPI = () => {
  return api.post('/confirm_prescan').then(response => response.data);
};

export default api