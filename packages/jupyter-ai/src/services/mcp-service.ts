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
      const response = await requestAPI<IMcpServer[]>('mcp/servers');
      return response;
    } catch (error) {
      console.error('Error fetching MCP servers:', error);
      return [];
    }
  }

  /**
   * Fetch available MCP commands for slash command autocomplete
   */
  async getCommands(): Promise<IMcpCommand[]> {
    try {
      const response = await requestAPI<IMcpCommand[]>('mcp/commands');
      return response;
    } catch (error) {
      console.error('Error fetching MCP commands:', error);
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
    command: string = '',
    args: string = ''
  ): Promise<IMcpCommandResult> {
    try {
      const response = await requestAPI<IMcpCommandResult>('mcp/execute', 'POST', {
        serverName,
        command,
        args
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