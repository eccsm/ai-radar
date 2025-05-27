import React, { useState } from 'react';
import {
  Box,
  Typography,
  TextField,
  Button,
  Card,
  CardContent,
  Grid,
  Chip,
  CircularProgress,
  Alert,
  InputAdornment,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import apiService from '../api/apiService';

const SearchPage = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState(null);

  const handleSearch = async (e) => {
    e.preventDefault();
    
    if (!query.trim() || query.trim().length < 3) {
      setError('Please enter a search term with at least 3 characters');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      
      const response = await apiService.searchArticles(query);
      setResults(response.data);
      setSearched(true);
    } catch (err) {
      console.error('Error searching articles:', err);
      setError('Failed to perform search. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        <SearchIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
        Search Articles
      </Typography>
      
      <Typography variant="subtitle1" color="textSecondary" paragraph>
        Search for articles by title, content, or keywords
      </Typography>

      <Box 
        component="form" 
        onSubmit={handleSearch} 
        sx={{ mb: 4, display: 'flex', alignItems: 'flex-start', gap: 2 }}
      >
        <TextField
          fullWidth
          label="Search Term"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          variant="outlined"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
          helperText="Enter at least 3 characters"
          error={error && query.trim().length < 3}
        />
        <Button 
          type="submit" 
          variant="contained" 
          disabled={loading || query.trim().length < 3}
          sx={{ height: 56 }}
        >
          {loading ? <CircularProgress size={24} /> : 'Search'}
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {loading && (
        <Box display="flex" justifyContent="center" my={4}>
          <CircularProgress />
        </Box>
      )}

      {searched && !loading && results.length === 0 && (
        <Alert severity="info">
          No articles found matching your search term.
        </Alert>
      )}

      <Grid container spacing={3}>
        {results.map((article) => (
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

export default SearchPage;
