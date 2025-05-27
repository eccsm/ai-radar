import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box';

// Auth Context
import { AuthProvider, useAuth } from './contexts/AuthContext';
import PrivateRoute from './components/PrivateRoute';
import Login from './components/Login';

// Import components
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';

// Import pages
import Dashboard from './pages/Dashboard';
import TrendingArticles from './pages/TrendingArticles';
import ArticleExplorer from './pages/ArticleExplorer';
import SourceAnalysis from './pages/SourceAnalysis';
import SearchPage from './pages/SearchPage';
import ManageSources from './pages/ManageSources';

// Create theme
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
    },
  },
  typography: {
    fontFamily: [
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif',
    ].join(','),
  },
});

function MainLayout() {
  const [open, setOpen] = React.useState(true);
  const { logout } = useAuth();

  const toggleDrawer = () => {
    setOpen(!open);
  };

  const handleLogout = () => {
    logout();
  };

  return (
    <Box sx={{ display: 'flex' }}>
      <Navbar open={open} toggleDrawer={toggleDrawer} onLogout={handleLogout} />
      <Sidebar open={open} />
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          height: '100vh',
          overflow: 'auto',
          p: 3,
          pt: 10,
        }}
      >
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/trending" element={<TrendingArticles />} />
          <Route path="/articles" element={<ArticleExplorer />} />
          <Route path="/sources" element={<SourceAnalysis />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/manage-sources" element={<ManageSources />} />
        </Routes>
      </Box>
    </Box>
  );
}

function App() {
  return (
    <AuthProvider>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={
            <PrivateRoute>
              <MainLayout />
            </PrivateRoute>
          } />
        </Routes>
      </ThemeProvider>
    </AuthProvider>
  );
}

export default App;
