import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000',
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry && originalRequest.url !== '/api/v1/users/login') {
      originalRequest._retry = true;
      
      // Offline fallback: if no internet, use the 30-day offline token instead of trying to refresh
      if (!navigator.onLine) {
        const offlineToken = localStorage.getItem('offline_access_token');
        if (offlineToken) {
          originalRequest.headers.Authorization = `Bearer ${offlineToken}`;
          return api(originalRequest);
        } else {
          // No offline token, cannot proceed
          window.dispatchEvent(new CustomEvent('offline-auth-expired'));
          return Promise.reject(error);
        }
      }

      const refreshToken = localStorage.getItem('refresh_token');
      
      if (refreshToken) {
        try {
          const res = await axios.post(`${api.defaults.baseURL}/api/v1/users/refresh`, {
            refresh_token: refreshToken
          });
          
          if (res.data.status === 'success') {
            const newAccessToken = res.data.data.access_token;
            const newRefreshToken = res.data.data.refresh_token;
            
            localStorage.setItem('access_token', newAccessToken);
            if (newRefreshToken) localStorage.setItem('refresh_token', newRefreshToken);
            
            originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
            return api(originalRequest);
          }
        } catch (refreshError) {
          // Refresh token is invalid/expired
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('offline_access_token');
          localStorage.removeItem('user');
          window.location.href = '/login';
          return Promise.reject(refreshError);
        }
      } else {
        // No refresh token available
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;
