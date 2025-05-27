import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Chip,
  CircularProgress,
  Alert,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
} from '@mui/material';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import SourceIcon from '@mui/icons-material/Source';
import apiService from '../api/apiService';

// Register ChartJS components
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
);

const SourceAnalysis = () => {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [orderBy, setOrderBy] = useState('article_count');
  const [order, setOrder] = useState('desc');

  useEffect(() => {
    const fetchSources = async () => {
      try {
        setLoading(true);
        const response = await apiService.getAllSources();
        setSources(response.data);
        setError(null);
      } catch (err) {
        console.error('Error fetching sources:', err);
        setError('Failed to load source data. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchSources();
  }, []);

  const handleRequestSort = (property) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    return date.toLocaleDateString();
  };

  // Sort the sources based on the current sort settings
  const sortedSources = React.useMemo(() => {
    if (!sources) return [];
    
    return [...sources].sort((a, b) => {
      const aValue = a[orderBy];
      const bValue = b[orderBy];
      
      // Handle nulls
      if (aValue === null && bValue === null) return 0;
      if (aValue === null) return 1;
      if (bValue === null) return -1;
      
      // For dates
      if (orderBy === 'last_fetched_at') {
        return order === 'asc' 
          ? new Date(aValue) - new Date(bValue)
          : new Date(bValue) - new Date(aValue);
      }
      
      // For strings
      if (typeof aValue === 'string') {
        return order === 'asc'
          ? aValue.localeCompare(bValue)
          : bValue.localeCompare(aValue);
      }
      
      // For numbers
      return order === 'asc' ? aValue - bValue : bValue - aValue;
    });
  }, [sources, orderBy, order]);

  // Prepare chart data
  const chartData = React.useMemo(() => {
    if (!sources || sources.length === 0) return null;
    
    // Get top 10 sources by article count
    const topSources = [...sources]
      .sort((a, b) => b.article_count - a.article_count)
      .slice(0, 10);
    
    return {
      labels: topSources.map(source => source.name),
      datasets: [
        {
          label: 'Article Count',
          data: topSources.map(source => source.article_count),
          backgroundColor: 'rgba(54, 162, 235, 0.6)',
          borderColor: 'rgba(54, 162, 235, 1)',
          borderWidth: 1,
        },
      ],
    };
  }, [sources]);

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top',
      },
      title: {
        display: true,
        text: 'Top Sources by Article Count',
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        title: {
          display: true,
          text: 'Number of Articles',
        },
      },
    },
  };

  if (loading && sources.length === 0) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="80vh">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        <SourceIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
        Source Analysis
      </Typography>
      
      <Typography variant="subtitle1" color="textSecondary" paragraph>
        Analyze performance and statistics of content sources
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {loading && (
        <Box display="flex" justifyContent="center" my={2}>
          <CircularProgress size={30} />
        </Box>
      )}

      <Grid container spacing={3}>
        {/* Chart for top sources */}
        <Grid item xs={12}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Top Sources by Article Count
            </Typography>
            
            {chartData ? (
              <Box sx={{ height: 400 }}>
                <Bar data={chartData} options={chartOptions} />
              </Box>
            ) : (
              <Typography variant="body2" color="textSecondary">
                No source data available for chart
              </Typography>
            )}
          </Paper>
        </Grid>

        {/* Source Data Table */}
        <Grid item xs={12}>
          <Paper sx={{ width: '100%', overflow: 'hidden' }}>
            <TableContainer sx={{ maxHeight: 500 }}>
              <Table stickyHeader aria-label="source analysis table">
                <TableHead>
                  <TableRow>
                    <TableCell>
                      <TableSortLabel
                        active={orderBy === 'name'}
                        direction={orderBy === 'name' ? order : 'asc'}
                        onClick={() => handleRequestSort('name')}
                      >
                        Source Name
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>
                      <TableSortLabel
                        active={orderBy === 'last_fetched_at'}
                        direction={orderBy === 'last_fetched_at' ? order : 'asc'}
                        onClick={() => handleRequestSort('last_fetched_at')}
                      >
                        Last Fetched
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>
                      <TableSortLabel
                        active={orderBy === 'article_count'}
                        direction={orderBy === 'article_count' ? order : 'asc'}
                        onClick={() => handleRequestSort('article_count')}
                      >
                        Article Count
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>Status</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sortedSources.map((source) => (
                    <TableRow key={source.id} hover>
                      <TableCell>{source.name}</TableCell>
                      <TableCell>{source.source_type.toUpperCase()}</TableCell>
                      <TableCell>{formatDate(source.last_fetched_at)}</TableCell>
                      <TableCell>{source.article_count}</TableCell>
                      <TableCell>
                        <Chip 
                          label={source.active ? 'Active' : 'Inactive'} 
                          color={source.active ? 'success' : 'default'}
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                  {sortedSources.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} align="center">
                        No sources found
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default SourceAnalysis;
