import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../lib/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is logged in on mount
    const checkAuth = async () => {
      const storedUser = localStorage.getItem('user');
      if (storedUser) {
        setUser(JSON.parse(storedUser));
      }
      setLoading(false);
    };
    checkAuth();
  }, []);

  const login = async (email, password) => {
    try {
      const response = await api.post('/api/v1/users/login', { email, password });
      if (response.data.status === 'success') {
        // Set tokens
        localStorage.setItem('access_token', response.data.data.access_token);
        if (response.data.data.refresh_token) {
          localStorage.setItem('refresh_token', response.data.data.refresh_token);
        }
        if (response.data.data.offline_token) {
          localStorage.setItem('offline_access_token', response.data.data.offline_token);
        }
        
        // Fetch user details
        const meResponse = await api.get('/api/v1/users/me');
        if (meResponse.data.status === 'success') {
          const userData = meResponse.data.data;
          setUser(userData);
          localStorage.setItem('user', JSON.stringify(userData));
          return userData;
        }
      }
      throw new Error(response.data.message || 'Login failed');
    } catch (error) {
      console.error('Login error:', error);
      throw error;
    }
  };

  const register = async (email, password, fullName) => {
    try {
      const response = await api.post('/api/v1/users/register', { 
        email, 
        password, 
        full_name: fullName 
      });
      if (response.data.status === 'success') {
        return await login(email, password);
      }
      throw new Error(response.data.message || 'Registration failed');
    } catch (error) {
      console.error('Registration error:', error);
      throw error;
    }
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('offline_access_token');
    localStorage.removeItem('user');
    setUser(null);
    window.location.href = '/login';
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {!loading && children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
