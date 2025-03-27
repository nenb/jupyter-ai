/**
 * MCP service for interacting with MCP servers
 */

import { requestAPI } from '../handler';
import { IMcpServer, IMcpCommand, IMcpCommandResult } from '../types/mcp';

/**
 * Service for managing MCP server interactions
 */
export class McpService {
  /**
   * Fetch available MCP servers
   */
  async getServers(): Promise<IMcpServer[]> {
    try {
      console.log('Requesting MCP servers from API...');
      const response = await requestAPI<IMcpServer[]>('mcp/servers');
      console.log('MCP servers response:', response);
      return Array.isArray(response) ? response : [];
    } catch (error) {
      console.error('Error fetching MCP servers:', error);
      
      // Check specifically for 404 to handle when MCP is not available
      if (
        error instanceof Error && 
        'response' in error && 
        (error as any).response?.status === 404
      ) {
        console.log('MCP servers endpoint not found (404) - MCP may not be enabled');
        throw new Error('MCP not available');
      }
      
      // For server errors, may be temporary
      throw error;
    }
  }

  /**
   * Fetch available MCP commands for slash command autocomplete
   */
  async getCommands(): Promise<IMcpCommand[]> {
    try {
      console.log('Requesting MCP commands from API...');
      const response = await requestAPI<IMcpCommand[]>('mcp/commands');
      console.log('MCP commands response:', response);
      return Array.isArray(response) ? response : [];
    } catch (error) {
      console.error('Error fetching MCP commands:', error);
      
      // Check specifically for 404 to handle when MCP is not available
      if (
        error instanceof Error && 
        'response' in error && 
        (error as any).response?.status === 404
      ) {
        console.log('MCP commands endpoint not found (404) - MCP may not be enabled');
        throw new Error('MCP not available');
      }
      
      // For server errors, may be temporary
      throw error;
    }
  }
  
  /**
   * Fetch argument suggestions for MCP commands
   * 
   * @param command The MCP command to get suggestions for
   */
  async getCommandArguments(command: string): Promise<any[]> {
    try {
      const response = await requestAPI<any[]>(
        `mcp/arguments?command=${encodeURIComponent(command)}`
      );
      return response;
    } catch (error) {
      console.error('Error fetching MCP command arguments:', error);
      return [];
    }
  }

  /**
   * Execute an MCP command
   * 
   * @param serverName The name of the MCP server
   * @param command Optional specific command name
   * @param args Arguments for the command
   */
  async executeCommand(
    serverName: string,
    command: string = ''
  ): Promise<IMcpCommandResult> {
    try {
      const response = await requestAPI<IMcpCommandResult>('mcp/execute', {
        method: 'POST',
        body: JSON.stringify({
          serverName,
          command
        })
      });
      return response;
    } catch (error) {
      console.error('Error executing MCP command:', error);
      return {
        type: 'text',
        content: `Error executing command: ${error instanceof Error ? error.message : 'Unknown error'}`
      };
    }
  }
}

// Export a singleton instance
export const mcpService = new McpService();