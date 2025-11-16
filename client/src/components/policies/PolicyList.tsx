import React, { useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  Menu,
  MenuItem,
  Typography,
  Box,
  Alert,
  Tooltip,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import {
  MoreVert as MoreVertIcon,
  Edit as EditIcon,
  PlayArrow as ActivateIcon,
  Stop as DeactivateIcon,
  History as VersionHistoryIcon,
  Warning as ConflictIcon,
  Launch as ViewIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { usePolicies } from '../../hooks/usePolicies';
import { Policy, PolicyStatus, PolicyType } from '../../types/policy';
import { formatDistanceToNow } from 'date-fns';

interface PolicyListProps {
  filters?: {
    policy_type?: PolicyType;
    status?: PolicyStatus;
    include_inactive?: boolean;
  };
}

const statusColors: Record<PolicyStatus, string> = {
  [PolicyStatus.DRAFT]: 'default',
  [PolicyStatus.ACTIVE]: 'success',
  [PolicyStatus.INACTIVE]: 'default',
  [PolicyStatus.ARCHIVED]: 'warning',
  [PolicyStatus.SUPERSEDED]: 'error',
};

const typeColors: Record<PolicyType, string> = {
  [PolicyType.PRICING]: 'primary',
  [PolicyType.DISCOUNT]: 'secondary',
  [PolicyType.PAYMENT_TERMS]: 'info',
  [PolicyType.PRICE_FLOOR]: 'warning',
  [PolicyType.APPROVAL_MATRIX]: 'success',
  [PolicyType.SLA]: 'error',
  [PolicyType.CUSTOM]: 'default',
};

export const PolicyList: React.FC<PolicyListProps> = ({ filters }) => {
  const navigate = useNavigate();
  const { policies, loading, error, activatePolicy, deactivatePolicy, deletePolicy } = usePolicies(filters);
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const handleMenuClick = (event: React.MouseEvent<HTMLElement>, policy: Policy) => {
    setAnchorEl(event.currentTarget);
    setSelectedPolicy(policy);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
    setSelectedPolicy(null);
  };

  const handleActivate = async () => {
    if (selectedPolicy) {
      try {
        await activatePolicy(selectedPolicy.id);
      } catch (error) {
        console.error('Failed to activate policy:', error);
      }
      handleMenuClose();
    }
  };

  const handleDeactivate = async () => {
    if (selectedPolicy) {
      try {
        await deactivatePolicy(selectedPolicy.id);
      } catch (error) {
        console.error('Failed to deactivate policy:', error);
      }
      handleMenuClose();
    }
  };

  const handleDelete = () => {
    setDeleteDialogOpen(true);
    handleMenuClose();
  };

  const confirmDelete = async () => {
    if (selectedPolicy) {
      try {
        await deletePolicy(selectedPolicy.id);
      } catch (error) {
        console.error('Failed to delete policy:', error);
      }
    }
    setDeleteDialogOpen(false);
    setSelectedPolicy(null);
  };

  const handleEdit = () => {
    if (selectedPolicy) {
      navigate(`/policies/${selectedPolicy.id}/edit`);
    }
    handleMenuClose();
  };

  const handleView = () => {
    if (selectedPolicy) {
      navigate(`/policies/${selectedPolicy.id}`);
    }
    handleMenuClose();
  };

  const handleVersionHistory = () => {
    if (selectedPolicy) {
      navigate(`/policies/${selectedPolicy.id}/versions`);
    }
    handleMenuClose();
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={4}>
        <Typography>Loading policies...</Typography>
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        {error}
      </Alert>
    );
  }

  return (
    <>
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Policy Name</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Version</TableCell>
              <TableCell>Priority</TableCell>
              <TableCell>Created By</TableCell>
              <TableCell>Last Updated</TableCell>
              <TableCell>Conflicts</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {policies.map((policy) => (
              <TableRow key={policy.id} hover>
                <TableCell>
                  <Box>
                    <Typography variant="subtitle2" fontWeight="bold">
                      {policy.name}
                    </Typography>
                    {policy.description && (
                      <Typography variant="caption" color="textSecondary">
                        {policy.description}
                      </Typography>
                    )}
                  </Box>
                </TableCell>
                <TableCell>
                  <Chip
                    label={policy.policy_type.replace('_', ' ').toUpperCase()}
                    color={typeColors[policy.policy_type] as any}
                    size="small"
                  />
                </TableCell>
                <TableCell>
                  <Chip
                    label={policy.status.replace('_', ' ').toUpperCase()}
                    color={statusColors[policy.status] as any}
                    size="small"
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="body2">{policy.version}</Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">{policy.priority}</Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">{policy.created_by}</Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="caption">
                    {formatDistanceToNow(new Date(policy.updated_at), { addSuffix: true })}
                  </Typography>
                </TableCell>
                <TableCell>
                  {policy.conflict_count > 0 ? (
                    <Tooltip title={`${policy.conflict_count} conflict(s)`}>
                      <Chip
                        icon={<ConflictIcon />}
                        label={policy.conflict_count}
                        color="error"
                        size="small"
                        onClick={() => navigate(`/policies/${policy.id}/conflicts`)}
                        sx={{ cursor: 'pointer' }}
                      />
                    </Tooltip>
                  ) : (
                    <Typography variant="body2" color="success.main">
                      No conflicts
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <IconButton
                    onClick={(e) => handleMenuClick(e, policy)}
                    size="small"
                  >
                    <MoreVertIcon />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Actions Menu */}
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleMenuClose}
      >
        <MenuItem onClick={handleView}>
          <ViewIcon sx={{ mr: 1 }} />
          View Details
        </MenuItem>

        {selectedPolicy?.status === PolicyStatus.DRAFT && (
          <MenuItem onClick={handleEdit}>
            <EditIcon sx={{ mr: 1 }} />
            Edit Policy
          </MenuItem>
        )}

        {selectedPolicy?.status === PolicyStatus.INACTIVE && (
          <MenuItem onClick={handleActivate}>
            <ActivateIcon sx={{ mr: 1 }} />
            Activate Policy
          </MenuItem>
        )}

        {selectedPolicy?.status === PolicyStatus.ACTIVE && (
          <MenuItem onClick={handleDeactivate}>
            <DeactivateIcon sx={{ mr: 1 }} />
            Deactivate Policy
          </MenuItem>
        )}

        <MenuItem onClick={handleVersionHistory}>
          <VersionHistoryIcon sx={{ mr: 1 }} />
          Version History
        </MenuItem>

        {(selectedPolicy?.status === PolicyStatus.DRAFT || selectedPolicy?.status === PolicyStatus.INACTIVE) && (
          <MenuItem onClick={handleDelete} sx={{ color: 'error.main' }}>
            Delete Policy
          </MenuItem>
        )}
      </Menu>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Confirm Policy Deletion</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete the policy "{selectedPolicy?.name}"?
            This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button onClick={confirmDelete} color="error" variant="contained">
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};