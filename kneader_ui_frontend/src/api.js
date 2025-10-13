import axios from 'axios'

// Direct connection to Flask on port 5000
const API_BASE_URL = 'http://127.0.0.1:5000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000
})

// === Automatically attach JWT token ===
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
);
// Add response interceptor to handle errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error)
    throw error
  }
)
//export const login = (username, password) => {
  //return axios.post('http://127.0.0.1:5000/api/login', { username, password })
    //.then(response => response.data)
//}

// === AUTH ===
export const login = async (username, password) => {
  const res = await api.post('/login', { username, password })
  const { token } = res.data
  if (token) {
    localStorage.setItem('token', token)
  }
  return res.data
}

export const getStatus = () => {
  return api.get('/status').then(response => response.data)
}

export const scanItem = (barcode) => {
  return api.post('/scan', { barcode }).then(response => response.data)
}

export const abortProcess = () => {
  return api.post('/abort').then(response => response.data)
}

export const resumeProcess = () => {
  return api.post('/resume').then(response => response.data)
}
export const completeAbortProcess = () => {
  console.log('Sending complete_abort request to backend');
  return api.post('/complete_abort')
    .then(response => {
      console.log('Complete abort API response received:', response.data);
      return response.data;
    })
    .catch(error => {
      console.error('Complete abort API error:', error);
      return { status: 'error', message: 'API call failed' };
    });
}
export const cancelProcess = () => {
  console.log('Sending cancel request to backend');
  return api.post('/cancel')
    .then(response => {
      console.log('Cancel API response received:', response.data);
      return response.data;
    })
    .catch(error => {
      console.error('Cancel API error:', error);
      return { status: 'error', message: 'Cancel API call failed' };
    });
};




export const resetProcess = () => {
  return api.post('/reset').then(response => response.data)
}


export const getWorkorders = () => {
  return api.get('/workorders').then(response => response.data)
}

export const checkTransitions = () => {
  return api.get('/check_transitions').then(response => response.data)
}

export const getBatches = () => {
  return api.get(`/batches/${batch_number}`).then(response => response.data);
};

export const loadWorkorder = ({ batchNumber, batchType }) => {
  return api.post('/load_workorder', { batchNumber, batchType })
    .then(response => response.data)
    .catch(error => {
      console.error('API Error loading workorder:', error);
      return { status: 'error', message: 'Failed to load workorder' };
    });
};
export const confirmCompletion = () => {
  return api.post('/confirm_completion')
    .then(response => response.data)
    .catch(error => {
      console.error('API Error confirming completion:', error);
      return { status: 'error', message: 'Failed to confirm completion' };
    });
};


export const prescanItem = (barcode) => {
  return api.post('/prescan', { 'barcode':barcode }).then(response => response.data);
};
export const saveWorkorder = () => {
  console.log('Sending save_workorder request to backend');
  return api.post('/save_workorder')
    .then(response => {
      console.log('Save workorder API response:', response.data);
      return response.data;
    })
    .catch(error => {
      console.error('Save workorder API error:', error);
      return { status: 'error', message: 'Failed to save workorder' };
    });
};


export const confirmPrescanAPI = () => {
  return api.post('/confirm_prescan').then(response => response.data);
};

export default api