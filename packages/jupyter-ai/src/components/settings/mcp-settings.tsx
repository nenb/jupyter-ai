/**
 * MCP Settings Component
 * 
 * Displays MCP servers and their capabilities in the settings UI
 */

import React, { useEffect, useState } from 'react';
import { 
  Box, 
  Typography, 
  CircularProgress, 
  List, 
  ListItem, 
  ListItemText,
  Chip,
  Paper
} from '@mui/material';
import { IMcpServer } from '../../types/mcp';
import { mcpService } from '../../services/mcp-service';

/**
 * MCP Settings panel component
 */
export const McpSettings: React.FC = () => {
  const [servers, setServers] = useState<IMcpServer[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  
  useEffect(() => {
    // Add a delay for the first load to allow the backend to initialize
    const initialDelay = retryCount === 0 ? 1000 : 0;
    
    const fetchServers = async () => {
      try {
        if (retryCount === 0) {
          setIsLoading(true);
        }
        setError(null);
        
        console.log('Fetching MCP servers...');
        const serverList = await mcpService.getServers();
        console.log('MCP servers fetched successfully:', serverList);
        setServers(serverList);
      } catch (err) {
        console.error('Error fetching MCP servers:', err);
        
        // If we've tried less than 3 times, retry after a delay
        if (retryCount < 3) {
          setRetryCount(prev => prev + 1);
          setTimeout(() => {
            fetchServers();
          }, 2000); // Retry after 2 seconds
          
          setError('Loading MCP servers, please wait...');
        } else {
          setError(
            'Failed to load MCP servers. Make sure MCP servers are properly configured and restart JupyterLab if needed.'
          );
        }
      } finally {
        setIsLoading(false);
      }
    };
    
    // Add initial delay to allow backend initialization
    const timer = setTimeout(() => {
      fetchServers();
    }, initialDelay);
    
    return () => clearTimeout(timer);
  }, []);
  
  return (
    <Box className="jp-AI-mcpSettings">
      <Typography variant="h6" gutterBottom>
        MCP Servers
      </Typography>
      
      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
          <CircularProgress size={24} /> 
          <Typography sx={{ ml: 2 }}>Loading MCP servers...</Typography>
        </Box>
      ) : error ? (
        <Typography color="error">{error}</Typography>
      ) : servers.length === 0 ? (
        <Typography>
          No MCP servers found. MCP servers provide additional context and tools for AI interactions.
        </Typography>
      ) : (
        <List className="jp-AI-mcpServerList">
          {servers.map(server => (
            <Paper 
              key={server.id} 
              className="jp-AI-mcpServer"
              elevation={0}
              sx={{ mb: 2 }}
            >
              <Typography variant="h6">{server.name}</Typography>
              <Typography variant="body2" color="textSecondary" paragraph>
                {server.description || 'No description available'}
              </Typography>
              
              <Box className="jp-AI-mcpServerCapabilities">
                {server.capabilities.prompts && (
                  <Chip 
                    label="Prompts" 
                    size="small" 
                    className="jp-AI-mcpCapability"
                    sx={{ mr: 1 }}
                  />
                )}
                {server.capabilities.resources && (
                  <Chip 
                    label="Resources" 
                    size="small" 
                    className="jp-AI-mcpCapability"
                    sx={{ mr: 1 }}
                  />
                )}
                {server.capabilities.tools && (
                  <Chip 
                    label="Tools" 
                    size="small" 
                    className="jp-AI-mcpCapability"
                    sx={{ mr: 1 }}
                  />
                )}
              </Box>
              
              {/* Show available commands if any */}
              {(server.prompts?.length > 0 || server.tools?.length > 0) && (
                <Box mt={2}>
                  <Typography variant="subtitle2">Available Commands:</Typography>
                  <List dense>
                    {server.prompts?.map(prompt => (
                      <ListItem key={`prompt-${prompt.name}`}>
                        <ListItemText 
                          primary={`/${server.name} ${prompt.name}`} 
                          secondary={prompt.description || 'Prompt'}
                        />
                      </ListItem>
                    ))}
                    {server.tools?.map(tool => (
                      <ListItem key={`tool-${tool.name}`}>
                        <ListItemText 
                          primary={`/${server.name} ${tool.name}`} 
                          secondary={tool.description || 'Tool'}
                        />
                      </ListItem>
                    ))}
                    {/* Direct server command */}
                    <ListItem>
                      <ListItemText 
                        primary={`/${server.name} [arguments]`} 
                        secondary="Direct server command"
                      />
                    </ListItem>
                  </List>
                </Box>
              )}
            </Paper>
          ))}
        </List>
      )}
      
      {servers.length > 0 && (
        <Box className="jp-AI-mcpSettingsHelp">
          <Typography variant="subtitle2">Using MCP Servers</Typography>
          <Typography variant="body2">
            MCP servers can be accessed via slash commands in the chat interface.
            Use <code>/{'{server-name}'} [arguments]</code> to execute commands.
          </Typography>
        </Box>
      )}
    </Box>
  );
};