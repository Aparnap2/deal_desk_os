import React, { useState } from 'react';
import {
  Box,
  Typography,
  Button,
  Paper,
  Grid,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  AppBar,
  Toolbar,
  Alert,
} from '@mui/material';
import {
  Add as AddIcon,
  FilterList as FilterIcon,
  FileDownload as ExportIcon,
  FileUpload as ImportIcon,
  Settings as SettingsIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { PolicyList } from '../components/policies/PolicyList';
import { PolicyType, PolicyStatus } from '../types/policy';

const PolicyManagement: React.FC = () => {
  const navigate = useNavigate();
  const [filters, setFilters] = useState({
    policy_type: '',
    status: '',
    include_inactive: false,
  });

  const handleFilterChange = (field: string, value: any) => {
    setFilters(prev => ({ ...prev, [field]: value }));
  };

  const handleCreatePolicy = () => {
    navigate('/policies/new');
  };

  const handleMigratePolicies = async () => {
    try {
      // Call migration endpoint
      navigate('/policies');
    } catch (error) {
      console.error('Migration failed:', error);
    }
  };

  return (
    <Box sx={{ flexGrow: 1 }}>
      <AppBar position="static" color="default" elevation={0}>
        <Toolbar>
          <Typography variant="h4" component="h1" sx={{ flexGrow: 1 }}>
            Policy Management
          </Typography>
          <Box sx={{ display: 'flex', gap: 2 }}>
            <Button
              variant="outlined"
              startIcon={<ImportIcon />}
              onClick={handleMigratePolicies}
            >
              Migrate JSON Policies
            </Button>
            <Button
              variant="outlined"
              startIcon={<ExportIcon />}
            >
              Export Policies
            </Button>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={handleCreatePolicy}
            >
              Create Policy
            </Button>
          </Box>
        </Toolbar>
      </AppBar>

      <Box sx={{ p: 3 }}>
        <Box display="flex" flexDirection={{ xs: 'column', md: 'row' }} gap={3}>
          {/* Filters */}
          <Box sx={{ minWidth: { xs: '100%', md: '300px' } }}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Filters
              </Typography>

              <FormControl fullWidth sx={{ mb: 2 }}>
                <InputLabel>Policy Type</InputLabel>
                <Select
                  value={filters.policy_type}
                  onChange={(e) => handleFilterChange('policy_type', e.target.value)}
                  label="Policy Type"
                >
                  <MenuItem value="">All Types</MenuItem>
                  {Object.values(PolicyType).map((type) => (
                    <MenuItem key={type} value={type}>
                      {type.replace('_', ' ').toUpperCase()}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <FormControl fullWidth sx={{ mb: 2 }}>
                <InputLabel>Status</InputLabel>
                <Select
                  value={filters.status}
                  onChange={(e) => handleFilterChange('status', e.target.value)}
                  label="Status"
                >
                  <MenuItem value="">All Statuses</MenuItem>
                  {Object.values(PolicyStatus).map((status) => (
                    <MenuItem key={status} value={status}>
                      {status.replace('_', ' ').toUpperCase()}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Paper>

            {/* Quick Stats */}
            <Paper sx={{ p: 2, mt: 2 }}>
              <Typography variant="h6" gutterBottom>
                Quick Stats
              </Typography>
              <Box>
                <Typography variant="body2" color="textSecondary">
                  Total Policies: {/* This would come from API */}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  Active Policies: {/* This would come from API */}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  Pending Conflicts: {/* This would come from API */}
                </Typography>
              </Box>
            </Paper>

            {/* Quick Actions */}
            <Paper sx={{ p: 2, mt: 2 }}>
              <Typography variant="h6" gutterBottom>
                Quick Actions
              </Typography>
              <Button
                fullWidth
                variant="outlined"
                size="small"
                startIcon={<SettingsIcon />}
                sx={{ mb: 1 }}
              >
                Manage Templates
              </Button>
              <Button
                fullWidth
                variant="outlined"
                size="small"
                startIcon={<FilterIcon />}
              >
                Advanced Filters
              </Button>
            </Paper>
          </Box>

          {/* Policy List */}
          <Box flex={1}>
            <Alert severity="info" sx={{ mb: 2 }}>
              <Typography variant="body2">
                Welcome to the Policy Management interface. Here you can create, edit, and manage
                business policies without requiring code deployments.
              </Typography>
            </Alert>

            <PolicyList filters={filters as any} />
          </Box>
        </Box>
      </Box>
    </Box>
  );
};

export default PolicyManagement;