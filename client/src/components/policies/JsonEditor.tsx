import React, { useState, useEffect } from 'react';
import { Box, Paper, Typography, Alert, TextField } from '@mui/material';

interface JsonEditorProps {
  value: Record<string, any>;
  onChange: (value: Record<string, any>) => void;
  height?: string;
  width?: string;
  readOnly?: boolean;
}

const JsonEditor: React.FC<JsonEditorProps> = ({
  value,
  onChange,
  height = '400px',
  width = '100%',
  readOnly = false,
}) => {
  const [editorValue, setEditorValue] = useState(JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const formatted = JSON.stringify(value, null, 2);
    if (formatted !== editorValue) {
      setEditorValue(formatted);
      setError(null);
    }
  }, [value]);

  const handleEditorChange = (newValue: string) => {
    setEditorValue(newValue);

    if (!readOnly) {
      try {
        const parsed = JSON.parse(newValue);
        setError(null);
        onChange(parsed);
      } catch (e) {
        setError(`Invalid JSON: ${e instanceof Error ? e.message : 'Unknown error'}`);
      }
    }
  };

  return (
    <Box>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
        <TextField
          multiline
          fullWidth
          value={editorValue}
          onChange={(e) => handleEditorChange(e.target.value)}
          variant="outlined"
          InputProps={{
            style: {
              fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
              fontSize: '14px',
              minHeight: height,
            },
          }}
          inputProps={{
            style: {
              minHeight: height,
              overflow: 'auto',
            },
          }}
          disabled={readOnly}
          placeholder="Enter JSON configuration..."
        />
      </Paper>

      {readOnly && (
        <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>
          This field is read-only
        </Typography>
      )}

      {!readOnly && (
        <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>
          Tip: Use proper JSON format with double quotes for keys and strings
        </Typography>
      )}
    </Box>
  );
};

export default JsonEditor;