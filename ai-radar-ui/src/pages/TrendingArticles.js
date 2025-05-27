import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Chip,
  Button,
  CircularProgress,
  Alert,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Link as MuiLink,
} from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import apiService from '../api/apiService';

const TrendingArticles = () => {
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState(7); // Default to 7 days

  useEffect(() => {
    const fetchTrendingArticles = async () => {
      try {
        setLoading(true);
        const response = await apiService.getTrendingArticles(timeRange);
        setArticles(response.data);
        setError(null);
      } catch (err) {
        console.error('Error fetching trending articles:', err);
        setError('Failed to load trending articles. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchTrendingArticles();
  }, [timeRange]);

  const handleTimeRangeChange = (event) => {
    setTimeRange(event.target.value);
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const getSentimentColor = (score) => {
    if (!score && score !== 0) return 'default';
    if (score > 0.3) return 'success';
    if (score < -0.3) return 'error';
    return 'warning';
  };

  const getSentimentLabel = (score) => {
    if (!score && score !== 0) return 'Unknown';
    if (score > 0.3) return 'Positive';
    if (score < -0.3) return 'Negative';
    return 'Neutral';
  };

  if (loading && articles.length === 0) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="80vh">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" gutterBottom>
          <TrendingUpIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
          Trending Articles
        </Typography>
        <FormControl sx={{ minWidth: 150 }}>
          <InputLabel id="time-range-select-label">Time Range</InputLabel>
          <Select
            labelId="time-range-select-label"
            id="time-range-select"
            value={timeRange}
            label="Time Range"
            onChange={handleTimeRangeChange}
          >
            <MenuItem value={1}>Last 24 Hours</MenuItem>
            <MenuItem value={7}>Last 7 Days</MenuItem>
            <MenuItem value={30}>Last 30 Days</MenuItem>
          </Select>
        </FormControl>
      </Box>

      <Typography variant="subtitle1" color="textSecondary" paragraph>
        Most important and trending AI news and research based on our scoring algorithm
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

      {!loading && articles.length === 0 && (
        <Alert severity="info">
          No trending articles found for the selected time period.
        </Alert>
      )}

      <Grid container spacing={3}>
        {articles.map((article) => (
          <Grid item xs={12} key={article.id}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  {article.title}
                </Typography>
                
                <Box display="flex" gap={1} mb={2} flexWrap="wrap">
                  <Chip 
                    label={`Source: ${article.source_name}`} 
                    size="small" 
                    variant="outlined"
                  />
                  <Chip 
                    label={`Published: ${formatDate(article.published_at)}`} 
                    size="small" 
                    variant="outlined"
                  />
                  <Chip 
                    label={`Fetched: ${formatDate(article.fetched_at)}`} 
                    size="small" 
                    variant="outlined"
                  />
                  {article.sentiment_score !== null && (
                    <Chip 
                      label={`Sentiment: ${getSentimentLabel(article.sentiment_score)}`}
                      color={getSentimentColor(article.sentiment_score)}
                      size="small"
                    />
                  )}
                  {article.importance_score !== null && (
                    <Chip 
                      label={`Importance: ${article.importance_score.toFixed(2)}`}
                      color="primary"
                      size="small"
                    />
                  )}
                </Box>
                
                {article.summary && (
                  <Typography variant="body2" color="textSecondary" paragraph>
                    {article.summary}
                  </Typography>
                )}
                
                <Box display="flex" justifyContent="flex-end">
                  <Button 
                    variant="outlined" 
                    startIcon={<OpenInNewIcon />}
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    size="small"
                  >
                    Read Article
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
};

export default TrendingArticles;
