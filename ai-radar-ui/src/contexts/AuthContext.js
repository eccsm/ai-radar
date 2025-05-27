import React, { createContext, useState, useContext, useEffect } from 'react';
import apiService from '../api/apiService';

const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [currentUser, setCurrentUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Load user data when token changes
  useEffect(() => {
    const loadUser = async () => {
      if (token) {
        try {
          const response = await apiService.getCurrentUser();
          setCurrentUser(response.data);
          setError(null);
        } catch (err) {
          console.error('Failed to load user data:', err);
          // If token is invalid, clear it
          if (err.response && err.response.status === 401) {
            logout();
          }
          setError('Session expired. Please login again.');
        }
      }
      setLoading(false);
    };

    loadUser();
  }, [token]);

  const login = async (username, password) => {
    setLoading(true);
    try {
      const response = await apiService.login(username, password);
      const { access_token } = response.data;
      
      // Save token to localStorage and state
      localStorage.setItem('token', access_token);
      setToken(access_token);
      
      // Get user data
      const userResponse = await apiService.getCurrentUser();
      setCurrentUser(userResponse.data);
      setError(null);
      return true;
    } catch (err) {
      console.error('Login failed:', err);
      setError(err.response?.data?.detail || 'Login failed. Please check your credentials.');
      return false;
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setCurrentUser(null);
  };

  const value = {
    currentUser,
    token,
    loading,
    error,
    login,
    logout,
    isAuthenticated: !!token
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
