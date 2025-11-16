import React, { useState, useEffect } from 'react';
import {
  Paper,
  Typography,
  Box,
  Grid,
  TextField,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Alert,
  CircularProgress,
  Tabs,
  Tab,
  Divider,
  Card,
  CardContent,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  Save as SaveIcon,
  Cancel as CancelIcon,
  Add as AddIcon,
  Delete as DeleteIcon,
  Visibility as PreviewIcon,
  History as VersionHistoryIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { usePolicy } from '../../hooks/usePolicies';
import { usePolicyTemplates } from '../../hooks/usePolicies';
import { usePolicyValidation } from '../../hooks/usePolicies';
import {
  Policy,
  PolicyType,
  PolicyStatus,
  PolicyConfigurationRequest,
  PolicyUpdateRequest,
  PolicyTemplate,
} from '../../types/policy';
import JsonEditor from './JsonEditor';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`policy-tabpanel-${index}`}
      aria-labelledby={`policy-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

interface PolicyEditorProps {
  policyId?: string;
}

const PolicyEditor: React.FC<PolicyEditorProps> = ({ policyId }) => {
  const navigate = useNavigate();
  const { id } = useParams();
  const actualPolicyId = policyId || id;

  const isEditing = Boolean(actualPolicyId);

  const { policy, loading: policyLoading, error: policyError, fetchPolicy } = usePolicy(actualPolicyId);
  const { templates, loading: templatesLoading } = usePolicyTemplates();
  const { validateConfiguration, validating, error: validationError } = usePolicyValidation();

  const [tabValue, setTabValue] = useState(0);
  const [formData, setFormData] = useState<PolicyConfigurationRequest>({
    name: '',
    description: '',
    policy_type: PolicyType.PRICING,
    configuration: {},
    priority: 0,
    tags: [],
  });

  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [validationWarnings, setValidationWarnings] = useState<string[]>([]);
  const [isDirty, setIsDirty] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [newTag, setNewTag] = useState('');

  useEffect(() => {
    if (policy) {
      setFormData({
        name: policy.name,
        description: policy.description || '',
        policy_type: policy.policy_type,
        configuration: policy.configuration,
        effective_at: policy.effective_at,
        expires_at: policy.expires_at,
        priority: policy.priority,
        tags: policy.tags || [],
      });
    }
  }, [policy]);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleFieldChange = (field: keyof PolicyConfigurationRequest, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setIsDirty(true);
  };

  const handleConfigurationChange = (configuration: Record<string, any>) => {
    setFormData(prev => ({ ...prev, configuration }));
    setIsDirty(true);
  };

  const handleTemplateSelect = (templateId: string) => {
    const template = templates.find(t => t.id === templateId);
    if (template) {
      setFormData(prev => ({
        ...prev,
        policy_type: template.policy_type,
        configuration: template.template_configuration,
      }));
      setSelectedTemplate(templateId);
    }
  };

  const handleAddTag = () => {
    if (newTag.trim() && !formData.tags?.includes(newTag.trim())) {
      setFormData(prev => ({
        ...prev,
        tags: [...(prev.tags || []), newTag.trim()],
      }));
      setNewTag('');
      setIsDirty(true);
    }
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setFormData(prev => ({
      ...prev,
      tags: prev.tags?.filter(tag => tag !== tagToRemove) || [],
    }));
    setIsDirty(true);
  };

  const handleValidate = async () => {
    try {
      const validation = await validateConfiguration({
        policy_type: formData.policy_type,
        configuration: formData.configuration,
      });

      setValidationErrors(validation.errors);
      setValidationWarnings(validation.warnings || []);
    } catch (error) {
      console.error('Validation failed:', error);
    }
  };

  const handleSave = async () => {
    try {
      // Validate before saving
      const validation = await validateConfiguration({
        policy_type: formData.policy_type,
        configuration: formData.configuration,
      });

      if (!validation.is_valid) {
        setValidationErrors(validation.errors);
        return;
      }

      // Save logic would go here
      setIsDirty(false);
      navigate('/policies');
    } catch (error) {
      console.error('Save failed:', error);
    }
  };

  const handleCancel = () => {
    if (isDirty) {
      // Show confirmation dialog
      navigate('/policies');
    } else {
      navigate('/policies');
    }
  };

  if (policyLoading) {
    return (
      <Box display="flex" justifyContent="center" p={4}>
        <CircularProgress />
      </Box>
    );
  }

  if (policyError) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        {policyError}
      </Alert>
    );
  }

  return (
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Paper sx={{ p: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
          <Typography variant="h4" component="h1">
            {isEditing ? 'Edit Policy' : 'Create New Policy'}
          </Typography>
          <Box>
            <Button
              variant="outlined"
              startIcon={<VersionHistoryIcon />}
              onClick={() => actualPolicyId && navigate(`/policies/${actualPolicyId}/versions`)}
              sx={{ mr: 2 }}
            >
              Version History
            </Button>
            <Button
              variant="outlined"
              startIcon={<CancelIcon />}
              onClick={handleCancel}
              sx={{ mr: 2 }}
            >
              Cancel
            </Button>
            <Button
              variant="contained"
              startIcon={validating ? <CircularProgress size={20} /> : <SaveIcon />}
              onClick={handleSave}
              disabled={!isDirty || validating}
            >
              {isEditing ? 'Update Policy' : 'Create Policy'}
            </Button>
          </Box>
        </Box>

        {validationError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {validationError}
          </Alert>
        )}

        <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
          <Tabs value={tabValue} onChange={handleTabChange}>
            <Tab label="Basic Information" />
            <Tab label="Configuration" />
            <Tab label="Validation" />
            {isEditing && <Tab label="Preview" />}
          </Tabs>
        </Box>

        <TabPanel value={tabValue} index={0}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Policy Name"
                value={formData.name}
                onChange={(e) => handleFieldChange('name', e.target.value)}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth required>
                <InputLabel>Policy Type</InputLabel>
                <Select
                  value={formData.policy_type}
                  onChange={(e) => handleFieldChange('policy_type', e.target.value)}
                >
                  {Object.values(PolicyType).map((type) => (
                    <MenuItem key={type} value={type}>
                      {type.replace('_', ' ').toUpperCase()}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                value={formData.description}
                onChange={(e) => handleFieldChange('description', e.target.value)}
                multiline
                rows={3}
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="Priority"
                type="number"
                value={formData.priority}
                onChange={(e) => handleFieldChange('priority', parseInt(e.target.value))}
                helperText="Higher priority policies override lower ones"
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <DatePicker
                label="Effective Date"
                value={formData.effective_at ? new Date(formData.effective_at) : null}
                onChange={(date) => handleFieldChange('effective_at', date?.toISOString())}
                slotProps={{ textField: { fullWidth: true } }}
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <DatePicker
                label="Expiration Date"
                value={formData.expires_at ? new Date(formData.expires_at) : null}
                onChange={(date) => handleFieldChange('expires_at', date?.toISOString())}
                slotProps={{ textField: { fullWidth: true } }}
              />
            </Grid>
            <Grid item xs={12}>
              <Typography variant="subtitle2" gutterBottom>
                Tags
              </Typography>
              <Box display="flex" flexWrap="wrap" gap={1} mb={2}>
                {formData.tags?.map((tag) => (
                  <Chip
                    key={tag}
                    label={tag}
                    onDelete={() => handleRemoveTag(tag)}
                    deleteIcon={<DeleteIcon />}
                  />
                ))}
              </Box>
              <Box display="flex" gap={1}>
                <TextField
                  size="small"
                  placeholder="Add a tag"
                  value={newTag}
                  onChange={(e) => setNewTag(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleAddTag()}
                />
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<AddIcon />}
                  onClick={handleAddTag}
                >
                  Add
                </Button>
              </Box>
            </Grid>

            {/* Template Selection */}
            <Grid item xs={12}>
              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle1" gutterBottom>
                Start from Template
              </Typography>
              <FormControl fullWidth>
                <InputLabel>Select Template</InputLabel>
                <Select
                  value={selectedTemplate}
                  onChange={(e) => handleTemplateSelect(e.target.value)}
                  disabled={templatesLoading}
                >
                  <MenuItem value="">None</MenuItem>
                  {templates
                    .filter(template => template.policy_type === formData.policy_type)
                    .map((template) => (
                      <MenuItem key={template.id} value={template.id}>
                        {template.name}
                      </MenuItem>
                    ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          <JsonEditor
            value={formData.configuration}
            onChange={handleConfigurationChange}
            height="500px"
          />
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">Policy Validation</Typography>
              <Button
                variant="outlined"
                startIcon={<PreviewIcon />}
                onClick={handleValidate}
                disabled={validating}
              >
                {validating ? 'Validating...' : 'Validate Policy'}
              </Button>
            </Box>

            {validationErrors.length > 0 && (
              <Alert severity="error" sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Validation Errors:
                </Typography>
                <ul>
                  {validationErrors.map((error, index) => (
                    <li key={index}>{error}</li>
                  ))}
                </ul>
              </Alert>
            )}

            {validationWarnings.length > 0 && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Validation Warnings:
                </Typography>
                <ul>
                  {validationWarnings.map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              </Alert>
            )}

            {validationErrors.length === 0 && validationWarnings.length === 0 && (
              <Alert severity="success">
                Policy configuration is valid!
              </Alert>
            )}
          </Box>
        </TabPanel>

        {isEditing && (
          <TabPanel value={tabValue} index={3}>
            <Typography variant="h6" gutterBottom>
              Policy Preview
            </Typography>
            <Card>
              <CardContent>
                <pre style={{ overflow: 'auto' }}>
                  {JSON.stringify(formData, null, 2)}
                </pre>
              </CardContent>
            </Card>
          </TabPanel>
        )}
      </Paper>
    </LocalizationProvider>
  );
};

export default PolicyEditor;