import React, { useState, useEffect } from 'react';
import {
  Grid,
  Paper,
  Typography,
  Box,
  Card,
  CardContent,
  Divider,
  CircularProgress,
  Alert,
} from '@mui/material';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import apiService from '../api/apiService';

// Register ChartJS components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

const Dashboard = () => {
  const [articleStats, setArticleStats] = useState(null);
  const [sourceStats, setSourceStats] = useState(null);
  const [timeSeriesData, setTimeSeriesData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        const [articlesResponse, sourcesResponse, timeSeriesResponse] = await Promise.all([
          apiService.getArticleStats(),
          apiService.getSourceStats(),
          apiService.getArticlesOverTime(),
        ]);

        setArticleStats(articlesResponse.data);
        setSourceStats(sourcesResponse.data);
        setTimeSeriesData(timeSeriesResponse.data);
        setError(null);
      } catch (err) {
        console.error('Error fetching dashboard data:', err);
        setError('Failed to load dashboard data. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  const prepareChartData = () => {
    if (!timeSeriesData) return null;

    // Sort data by date
    const sortedData = [...timeSeriesData].sort((a, b) => 
      new Date(a.date) - new Date(b.date)
    );

    return {
      labels: sortedData.map(item => {
        const date = new Date(item.date);
        return date.toLocaleDateString();
      }),
      datasets: [
        {
          label: 'Articles',
          data: sortedData.map(item => item.count),
          fill: false,
          backgroundColor: 'rgba(75, 192, 192, 0.2)',
          borderColor: 'rgba(75, 192, 192, 1)',
          tension: 0.4,
        },
      ],
    };
  };

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top',
      },
      title: {
        display: true,
        text: 'Articles Over Time',
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

  if (loading) {
    return (
      <Box
        display="flex"
        justifyContent="center"
        alignItems="center"
        minHeight="80vh"
      >
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box m={2}>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        AI Radar Dashboard
      </Typography>
      <Typography variant="subtitle1" color="textSecondary" paragraph>
        Real-time monitoring and analytics for AI news and research
      </Typography>
      
      <Grid container spacing={3}>
        {/* Article Statistics */}
        <Grid item xs={12} md={6}>
          <Paper
            sx={{
              p: 2,
              display: 'flex',
              flexDirection: 'column',
              height: 240,
            }}
          >
            <Typography variant="h6" gutterBottom>
              Article Statistics
            </Typography>
            {articleStats && (
              <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, justifyContent: 'space-around' }}>
                <Box display="flex" justifyContent="space-between">
                  <Typography>Total Articles:</Typography>
                  <Typography fontWeight="bold">{articleStats.total_articles}</Typography>
                </Box>
                <Divider />
                <Box display="flex" justifyContent="space-between">
                  <Typography>Last 24 Hours:</Typography>
                  <Typography fontWeight="bold">{articleStats.articles_last_day}</Typography>
                </Box>
                <Divider />
                <Box display="flex" justifyContent="space-between">
                  <Typography>Last Week:</Typography>
                  <Typography fontWeight="bold">{articleStats.articles_last_week}</Typography>
                </Box>
                <Divider />
                <Box display="flex" justifyContent="space-between">
                  <Typography>Last Month:</Typography>
                  <Typography fontWeight="bold">{articleStats.articles_last_month}</Typography>
                </Box>
                <Divider />
                <Box display="flex" justifyContent="space-between">
                  <Typography>Avg. Similarity Score:</Typography>
                  <Typography fontWeight="bold">
                    {articleStats.avg_similarity_score.toFixed(2)}
                  </Typography>
                </Box>
              </Box>
            )}
          </Paper>
        </Grid>

        {/* Source Statistics */}
        <Grid item xs={12} md={6}>
          <Paper
            sx={{
              p: 2,
              display: 'flex',
              flexDirection: 'column',
              height: 240,
            }}
          >
            <Typography variant="h6" gutterBottom>
              Source Statistics
            </Typography>
            {sourceStats && (
              <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, justifyContent: 'space-around' }}>
                <Box display="flex" justifyContent="space-between">
                  <Typography>Total Sources:</Typography>
                  <Typography fontWeight="bold">{sourceStats.total_sources}</Typography>
                </Box>
                <Divider />
                <Box display="flex" justifyContent="space-between">
                  <Typography>Active Sources:</Typography>
                  <Typography fontWeight="bold">{sourceStats.active_sources}</Typography>
                </Box>
                <Divider />
                <Box display="flex" justifyContent="space-between">
                  <Typography>Sources With Articles:</Typography>
                  <Typography fontWeight="bold">{sourceStats.sources_with_articles}</Typography>
                </Box>
              </Box>
            )}
          </Paper>
        </Grid>

        {/* Top Sources */}
        <Grid item xs={12} md={6}>
          <Paper
            sx={{
              p: 2,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 240,
            }}
          >
            <Typography variant="h6" gutterBottom>
              Top Sources
            </Typography>
            {sourceStats && sourceStats.top_sources.length > 0 ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {sourceStats.top_sources.map((source, index) => (
                  <Card key={index} variant="outlined">
                    <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
                      <Box display="flex" justifyContent="space-between" alignItems="center">
                        <Typography variant="body1">{source.name}</Typography>
                        <Typography variant="body2" color="textSecondary">
                          {source.article_count} articles
                        </Typography>
                      </Box>
                    </CardContent>
                  </Card>
                ))}
              </Box>
            ) : (
              <Typography variant="body2" color="textSecondary" sx={{ mt: 2 }}>
                No source data available
              </Typography>
            )}
          </Paper>
        </Grid>

        {/* Articles Over Time Chart */}
        <Grid item xs={12} md={6}>
          <Paper
            sx={{
              p: 2,
              display: 'flex',
              flexDirection: 'column',
              height: 240,
            }}
          >
            <Typography variant="h6" gutterBottom>
              Articles Over Time
            </Typography>
            {timeSeriesData && timeSeriesData.length > 0 ? (
              <Box sx={{ height: 170 }}>
                <Line data={prepareChartData()} options={chartOptions} />
              </Box>
            ) : (
              <Typography variant="body2" color="textSecondary" sx={{ mt: 2 }}>
                No time series data available
              </Typography>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;
