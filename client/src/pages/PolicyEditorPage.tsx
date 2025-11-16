import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Box } from '@mui/material';
import PolicyEditor from '../components/policies/PolicyEditor';

const PolicyEditorPage: React.FC = () => {
  const navigate = useNavigate();
  const { policyId } = useParams();

  return (
    <Box sx={{ flexGrow: 1, p: 3 }}>
      <PolicyEditor policyId={policyId} />
    </Box>
  );
};

export default PolicyEditorPage;