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
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Pagination,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import ArticleIcon from '@mui/icons-material/Article';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import FindInPageIcon from '@mui/icons-material/FindInPage';
import apiService from '../api/apiService';

const ArticleExplorer = () => {
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState(30); // Default to 30 days
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [selectedArticle, setSelectedArticle] = useState(null);
  const [similarArticles, setSimilarArticles] = useState([]);
  const [loadingSimilar, setLoadingSimilar] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  useEffect(() => {
    const fetchArticles = async () => {
      try {
        setLoading(true);
        // In a real implementation, you would add pagination parameters
        const response = await apiService.getTrendingArticles(timeRange, 20);
        setArticles(response.data);
        setTotalPages(Math.ceil(response.data.length / 5));
        setError(null);
      } catch (err) {
        console.error('Error fetching articles:', err);
        setError('Failed to load articles. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchArticles();
  }, [timeRange]);

  const handleTimeRangeChange = (event) => {
    setTimeRange(event.target.value);
    setPage(1);
  };

  const handlePageChange = (event, value) => {
    setPage(value);
  };

  const handleFindSimilar = async (article) => {
    try {
      setSelectedArticle(article);
      setLoadingSimilar(true);
      setDialogOpen(true);
      
      const response = await apiService.getSimilarArticles(article.id);
      setSimilarArticles(response.data);
    } catch (err) {
      console.error('Error fetching similar articles:', err);
      setSimilarArticles([]);
    } finally {
      setLoadingSimilar(false);
    }
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
    setSelectedArticle(null);
    setSimilarArticles([]);
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

  // Get paginated articles
  const paginatedArticles = articles.slice((page - 1) * 5, page * 5);

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
          <ArticleIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
          Article Explorer
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
            <MenuItem value={7}>Last 7 Days</MenuItem>
            <MenuItem value={30}>Last 30 Days</MenuItem>
            <MenuItem value={90}>Last 90 Days</MenuItem>
            <MenuItem value={365}>Last Year</MenuItem>
          </Select>
        </FormControl>
      </Box>

      <Typography variant="subtitle1" color="textSecondary" paragraph>
        Explore articles and find similar content based on semantic similarity
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
          No articles found for the selected time period.
        </Alert>
      )}

      <Grid container spacing={3}>
        {paginatedArticles.map((article) => (
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
                
                <Box display="flex" justifyContent="flex-end" gap={2}>
                  <Button 
                    variant="outlined" 
                    startIcon={<FindInPageIcon />}
                    onClick={() => handleFindSimilar(article)}
                    size="small"
                  >
                    Find Similar
                  </Button>
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

      {articles.length > 0 && (
        <Box display="flex" justifyContent="center" mt={4}>
          <Pagination
            count={totalPages}
            page={page}
            onChange={handlePageChange}
            color="primary"
          />
        </Box>
      )}

      {/* Similar Articles Dialog */}
      <Dialog
        open={dialogOpen}
        onClose={handleCloseDialog}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          Similar Articles
          {selectedArticle && (
            <Typography variant="subtitle2" color="textSecondary">
              Based on: {selectedArticle.title}
            </Typography>
          )}
        </DialogTitle>
        <DialogContent dividers>
          {loadingSimilar ? (
            <Box display="flex" justifyContent="center" my={3}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              {similarArticles.length === 0 ? (
                <Alert severity="info">
                  No similar articles found.
                </Alert>
              ) : (
                <Grid container spacing={2}>
                  {similarArticles.map((article) => (
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
                              label={`Similarity: ${(article.similarity_score * 100).toFixed(1)}%`}
                              color="primary"
                              size="small"
                            />
                          </Box>
                          
                          {article.summary && (
                            <Typography variant="body2" color="textSecondary" paragraph>
                              {article.summary.substring(0, 200)}
                              {article.summary.length > 200 ? '...' : ''}
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
              )}
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ArticleExplorer;
