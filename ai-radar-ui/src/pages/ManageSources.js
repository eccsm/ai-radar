import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  Grid,
  Chip,
  CircularProgress,
  Alert,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Switch,
  FormControlLabel,
  Divider,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import SettingsIcon from '@mui/icons-material/Settings';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import apiService from '../api/apiService';

const ManageSources = () => {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  
  // Add source state
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [newSourceName, setNewSourceName] = useState('');
  const [newSourceUrl, setNewSourceUrl] = useState('');
  const [newSourceActive, setNewSourceActive] = useState(true);
  const [addingSource, setAddingSource] = useState(false);
  
  // Edit source state
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editSourceId, setEditSourceId] = useState('');
  const [editSourceName, setEditSourceName] = useState('');
  const [editSourceUrl, setEditSourceUrl] = useState('');
  const [editSourceActive, setEditSourceActive] = useState(true);
  const [editingSource, setEditingSource] = useState(false);
  
  // Delete source state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteSourceId, setDeleteSourceId] = useState('');
  const [deleteSourceName, setDeleteSourceName] = useState('');
  const [deletingSource, setDeletingSource] = useState(false);

  useEffect(() => {
    fetchSources();
  }, []);

  const fetchSources = async () => {
    try {
      setLoading(true);
      const response = await apiService.getAllSources();
      setSources(response.data);
      setError(null);
    } catch (err) {
      console.error('Error fetching sources:', err);
      setError('Failed to load sources. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  // Add source handlers
  const handleOpenAddDialog = () => {
    setNewSourceName('');
    setNewSourceUrl('');
    setNewSourceActive(true);
    setAddDialogOpen(true);
  };

  const handleCloseAddDialog = () => {
    setAddDialogOpen(false);
  };

  const handleAddSource = async () => {
    if (!newSourceName.trim() || !newSourceUrl.trim()) {
      setError('Source name and URL are required');
      return;
    }

    try {
      setAddingSource(true);
      setError(null);
      
      await apiService.addSource(
        newSourceName.trim(),
        newSourceUrl.trim(),
        'rss',  // Currently only supporting RSS
        newSourceActive
      );
      
      // Refresh sources list
      await fetchSources();
      
      setSuccess(`Source "${newSourceName}" added successfully`);
      setAddDialogOpen(false);
      
      // Clear success message after 5 seconds
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error('Error adding source:', err);
      setError(err.response?.data?.detail || 'Failed to add source. Please try again.');
    } finally {
      setAddingSource(false);
    }
  };

  // Edit source handlers
  const handleOpenEditDialog = (source) => {
    setEditSourceId(source.id);
    setEditSourceName(source.name);
    setEditSourceUrl(source.url);
    setEditSourceActive(source.active);
    setEditDialogOpen(true);
  };

  const handleCloseEditDialog = () => {
    setEditDialogOpen(false);
  };

  const handleEditSource = async () => {
    if (!editSourceName.trim() || !editSourceUrl.trim()) {
      setError('Source name and URL are required');
      return;
    }

    try {
      setEditingSource(true);
      setError(null);
      
      await apiService.updateSource(
        editSourceId,
        editSourceName.trim(),
        editSourceUrl.trim(),
        'rss',  // Currently only supporting RSS
        editSourceActive
      );
      
      // Refresh sources list
      await fetchSources();
      
      setSuccess(`Source "${editSourceName}" updated successfully`);
      setEditDialogOpen(false);
      
      // Clear success message after 5 seconds
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error('Error updating source:', err);
      setError(err.response?.data?.detail || 'Failed to update source. Please try again.');
    } finally {
      setEditingSource(false);
    }
  };

  // Delete source handlers
  const handleOpenDeleteDialog = (source) => {
    setDeleteSourceId(source.id);
    setDeleteSourceName(source.name);
    setDeleteDialogOpen(true);
  };

  const handleCloseDeleteDialog = () => {
    setDeleteDialogOpen(false);
  };

  const handleDeleteSource = async () => {
    try {
      setDeletingSource(true);
      setError(null);
      
      await apiService.deleteSource(deleteSourceId);
      
      // Refresh sources list
      await fetchSources();
      
      setSuccess(`Source "${deleteSourceName}" deleted successfully`);
      setDeleteDialogOpen(false);
      
      // Clear success message after 5 seconds
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error('Error deleting source:', err);
      setError(err.response?.data?.detail || 'Failed to delete source. Please try again.');
    } finally {
      setDeletingSource(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    return date.toLocaleDateString();
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
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" gutterBottom>
          <SettingsIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
          Manage Sources
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={handleOpenAddDialog}
        >
          Add Source
        </Button>
      </Box>
      
      <Typography variant="subtitle1" color="textSecondary" paragraph>
        Add, edit, or remove content sources for AI Radar
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 3 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {loading && (
        <Box display="flex" justifyContent="center" my={2}>
          <CircularProgress size={30} />
        </Box>
      )}

      {!loading && sources.length === 0 && (
        <Alert severity="info">
          No sources found. Add your first source using the button above.
        </Alert>
      )}

      <Grid container spacing={3}>
        {sources.map((source) => (
          <Grid item xs={12} sm={6} md={4} key={source.id}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  {source.name}
                </Typography>
                
                <Typography variant="body2" color="textSecondary" gutterBottom noWrap>
                  {source.url}
                </Typography>
                
                <Box display="flex" gap={1} my={2} flexWrap="wrap">
                  <Chip 
                    label={`Type: ${source.source_type.toUpperCase()}`} 
                    size="small" 
                    variant="outlined"
                  />
                  <Chip 
                    label={source.active ? 'Active' : 'Inactive'} 
                    color={source.active ? 'success' : 'default'}
                    size="small"
                  />
                  <Chip 
                    label={`Articles: ${source.article_count}`}
                    color="primary"
                    size="small"
                  />
                </Box>
                
                <Typography variant="body2" color="textSecondary">
                  Last fetched: {formatDate(source.last_fetched_at)}
                </Typography>
                
                <Divider sx={{ my: 2 }} />
                
                <Box display="flex" justifyContent="space-between">
                  <Button 
                    variant="outlined" 
                    startIcon={<EditIcon />}
                    onClick={() => handleOpenEditDialog(source)}
                    size="small"
                  >
                    Edit
                  </Button>
                  <Button 
                    variant="outlined" 
                    color="error"
                    startIcon={<DeleteIcon />}
                    onClick={() => handleOpenDeleteDialog(source)}
                    size="small"
                  >
                    Delete
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Add Source Dialog */}
      <Dialog open={addDialogOpen} onClose={handleCloseAddDialog} maxWidth="sm" fullWidth>
        <DialogTitle>Add New Source</DialogTitle>
        <DialogContent>
          <Box component="form" noValidate sx={{ mt: 1 }}>
            <TextField
              margin="normal"
              required
              fullWidth
              id="name"
              label="Source Name"
              name="name"
              autoFocus
              value={newSourceName}
              onChange={(e) => setNewSourceName(e.target.value)}
            />
            <TextField
              margin="normal"
              required
              fullWidth
              id="url"
              label="RSS Feed URL"
              name="url"
              placeholder="https://example.com/feed.xml"
              value={newSourceUrl}
              onChange={(e) => setNewSourceUrl(e.target.value)}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={newSourceActive}
                  onChange={(e) => setNewSourceActive(e.target.checked)}
                  color="primary"
                />
              }
              label="Active"
              sx={{ mt: 2 }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseAddDialog}>Cancel</Button>
          <Button 
            onClick={handleAddSource} 
            variant="contained" 
            disabled={addingSource || !newSourceName.trim() || !newSourceUrl.trim()}
          >
            {addingSource ? <CircularProgress size={24} /> : 'Add Source'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Source Dialog */}
      <Dialog open={editDialogOpen} onClose={handleCloseEditDialog} maxWidth="sm" fullWidth>
        <DialogTitle>Edit Source</DialogTitle>
        <DialogContent>
          <Box component="form" noValidate sx={{ mt: 1 }}>
            <TextField
              margin="normal"
              required
              fullWidth
              id="edit-name"
              label="Source Name"
              name="name"
              value={editSourceName}
              onChange={(e) => setEditSourceName(e.target.value)}
            />
            <TextField
              margin="normal"
              required
              fullWidth
              id="edit-url"
              label="RSS Feed URL"
              name="url"
              value={editSourceUrl}
              onChange={(e) => setEditSourceUrl(e.target.value)}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={editSourceActive}
                  onChange={(e) => setEditSourceActive(e.target.checked)}
                  color="primary"
                />
              }
              label="Active"
              sx={{ mt: 2 }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseEditDialog}>Cancel</Button>
          <Button 
            onClick={handleEditSource} 
            variant="contained" 
            disabled={editingSource || !editSourceName.trim() || !editSourceUrl.trim()}
          >
            {editingSource ? <CircularProgress size={24} /> : 'Save Changes'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Source Dialog */}
      <Dialog open={deleteDialogOpen} onClose={handleCloseDeleteDialog}>
        <DialogTitle>Delete Source</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete the source "{deleteSourceName}"?
          </Typography>
          <Typography variant="body2" color="error" sx={{ mt: 2 }}>
            This action cannot be undone. All articles from this source will also be deleted.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDeleteDialog}>Cancel</Button>
          <Button 
            onClick={handleDeleteSource} 
            variant="contained" 
            color="error"
            disabled={deletingSource}
          >
            {deletingSource ? <CircularProgress size={24} /> : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ManageSources;
