/**
 * MCP Result Component
 * 
 * Renders MCP command results in the chat UI
 */

import React from 'react';
import { IMcpCommandResult } from '../types/mcp';
import { Box, Typography, Paper } from '@mui/material';

interface McpResultProps {
  result: IMcpCommandResult;
}

/**
 * Component to render MCP command results
 */
export const McpResult: React.FC<McpResultProps> = ({ result }) => {
  // Text result - most common type
  if (result.type === 'text') {
    return (
      <Box className="jp-AI-mcpResult jp-AI-mcpResult-text">
        <Box component="pre" sx={{ m: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {result.content}
        </Box>
      </Box>
    );
  }
  
  // Image result
  if (result.type === 'image' && result.content) {
    return (
      <Box className="jp-AI-mcpResult jp-AI-mcpResult-image">
        <img 
          src={`data:${result.mimeType || 'image/png'};base64,${result.content}`} 
          alt="MCP result" 
          style={{ maxWidth: '100%', height: 'auto' }}
        />
      </Box>
    );
  }
  
  // Resource result
  if (result.type === 'resource') {
    return (
      <Box className="jp-AI-mcpResult jp-AI-mcpResult-resource">
        <Box className="jp-AI-mcpResult-resourceHeader" sx={{ fontWeight: 'bold', mb: 1 }}>
          <Typography variant="caption">
            {result.metadata?.uri || 'Resource'}
          </Typography>
        </Box>
        <Box component="pre" sx={{ m: 0 }}>
          {result.content}
        </Box>
      </Box>
    );
  }
  
  // Fallback for unknown types
  return (
    <Box className="jp-AI-mcpResult jp-AI-mcpResult-unknown">
      <Box component="pre" sx={{ m: 0 }}>
        {JSON.stringify(result, null, 2)}
      </Box>
    </Box>
  );
};