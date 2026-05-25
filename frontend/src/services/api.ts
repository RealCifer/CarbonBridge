import axios from 'axios';

// The default configuration assumes the Django backend is running on 8000
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// For an MVP, we will assume a valid token is set in localStorage, 
// or we skip auth if the backend allows it for testing.
// In a real app, we'd add interceptors here to inject the Bearer token.
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
