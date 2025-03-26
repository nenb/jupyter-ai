/**
 * MCP Result Component
 * 
 * Renders MCP command results in the chat UI
 */

import React from 'react';
import { IMcpCommandResult } from '../types/mcp';
import { Box, Typography, Chip, Tooltip } from '@mui/material';
import ScienceIcon from '@mui/icons-material/Science';
import CodeIcon from '@mui/icons-material/Code';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';

interface McpResultProps {
  result: IMcpCommandResult;
  server?: string;
  command?: string;
  metadata?: Record<string, any>;
}

/**
 * Component to render MCP command results in the chat UI
 */
export const McpResult: React.FC<McpResultProps> = ({ 
  result, 
  server = "", 
  command = "", 
  metadata = {} 
}) => {
  // Default to the result itself if specific props aren't provided
  const resultType = result.type;
  const resultServer = server || metadata?.server || "";
  const resultCommand = command || metadata?.command || "";
  const resultMetadata = { ...metadata, ...(result.metadata || {}) };
  
  // Determine icon based on result type
  const getIcon = () => {
    switch(resultType) {
      case 'resource':
        return <ScienceIcon fontSize="small" />;
      case 'image':
        return <AutoFixHighIcon fontSize="small" />;
      default:
        return <CodeIcon fontSize="small" />;
    }
  };
  
  // Header with server and command information
  const renderHeader = () => {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
        <Tooltip title={`MCP Server: ${resultServer}`}>
          <Chip
            icon={getIcon()} 
            label={resultServer}
            size="small"
            sx={{ mr: 1 }}
          />
        </Tooltip>
        {resultCommand && (
          <Tooltip title={`Command: ${resultCommand}`}>
            <Typography variant="caption" color="text.secondary">
              {resultCommand}
            </Typography>
          </Tooltip>
        )}
      </Box>
    );
  };
  
  // Main content renderer
  const renderContent = () => {
    // Text result - most common type
    if (resultType === 'text') {
      return (
        <Box component="pre" 
          sx={{ 
            m: 0, 
            p: 1,
            whiteSpace: 'pre-wrap', 
            wordBreak: 'break-word',
            fontSize: '0.875rem',
            bgcolor: 'background.paper',
            borderRadius: 1,
            border: '1px solid',
            borderColor: 'divider'
          }}
        >
          {result.content}
        </Box>
      );
    }
    
    // Image result
    if (resultType === 'image' && result.content) {
      return (
        <Box sx={{ my: 1 }}>
          <img 
            src={`data:${result.mimeType || 'image/png'};base64,${result.content}`} 
            alt="MCP result" 
            style={{ maxWidth: '100%', height: 'auto', borderRadius: '4px' }}
          />
        </Box>
      );
    }
    
    // Resource result
    if (resultType === 'resource') {
      return (
        <Box 
          sx={{ 
            p: 1,
            bgcolor: 'background.paper',
            borderRadius: 1,
            border: '1px solid',
            borderColor: 'divider'
          }}
        >
          <Box sx={{ fontWeight: 'bold', mb: 1 }}>
            <Typography variant="caption">
              {resultMetadata?.uri || 'Resource'}
            </Typography>
          </Box>
          <Box component="pre" sx={{ m: 0, fontSize: '0.875rem' }}>
            {result.content}
          </Box>
        </Box>
      );
    }
    
    // Fallback for unknown types
    return (
      <Box component="pre" 
        sx={{ 
          m: 0, 
          p: 1,
          fontSize: '0.875rem',
          bgcolor: 'background.paper',
          borderRadius: 1,
          border: '1px solid',
          borderColor: 'divider'
        }}
      >
        {JSON.stringify(result, null, 2)}
      </Box>
    );
  };
  
  return (
    <Box className="jp-AI-mcpResult" sx={{ width: '100%' }}>
      {renderHeader()}
      {renderContent()}
    </Box>
  );
};

/**
 * Message adapter to extract MCP result from message metadata
 * 
 * @param message The message object from JupyterLab Chat
 * @returns JSX element with the rendered MCP result, or null if not an MCP result
 */
/**
 * Function to check if a message contains MCP results
 */
export const hasMcpResult = (message: any): boolean => {
  return message && message.metadata && message.metadata.mcp_result;
};

/**
 * Extract MCP result from message metadata
 */
export const extractMcpResult = (message: any): IMcpCommandResult | null => {
  if (!hasMcpResult(message)) {
    return null;
  }

  const metadata = message.metadata.mcp_result;
  return {
    type: metadata.type || 'text',
    content: message.body,
    mimeType: metadata.metadata?.mimeType,
    metadata: metadata.metadata
  };
};

/**
 * Renders an MCP result from a message
 */
export const renderMcpResult = (message: any): JSX.Element | null => {
  if (!hasMcpResult(message)) {
    return null;
  }

  const metadata = message.metadata.mcp_result;
  const result = extractMcpResult(message);
  
  if (!result) {
    return null;
  }

  return (
    <McpResult 
      result={result}
      server={metadata.server}
      command={metadata.command}
      metadata={metadata.metadata} 
    />
  );
};