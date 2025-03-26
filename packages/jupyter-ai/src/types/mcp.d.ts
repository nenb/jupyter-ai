/**
 * TypeScript declarations for MCP (Model Context Protocol) integration
 */

/**
 * MCP Server information returned by the backend
 */
export interface IMcpServer {
  id: string;
  name: string;
  description: string;
  status: string;
  capabilities: {
    prompts?: boolean;
    resources?: boolean;
    tools?: boolean;
  };
  tools: IMcpTool[];
  prompts: IMcpPrompt[];
  resources: IMcpResource[];
  connection_type: string;
}

/**
 * MCP Command information for slash commands
 */
export interface IMcpCommand {
  serverName: string;
  commandName: string;
  description: string;
  serverStatus: string;
  type?: 'prompt' | 'tool' | 'server';
}

/**
 * MCP Tool information
 */
export interface IMcpTool {
  name: string;
  description: string;
  inputSchema: any;
}

/**
 * MCP Prompt information
 */
export interface IMcpPrompt {
  name: string;
  description: string;
  arguments: IMcpPromptArgument[];
}

/**
 * MCP Prompt Argument information
 */
export interface IMcpPromptArgument {
  name: string;
  description: string;
  required: boolean;
}

/**
 * MCP Resource information
 */
export interface IMcpResource {
  uri: string;
  name: string;
  description: string;
}

/**
 * MCP Command Result
 */
export interface IMcpCommandResult {
  type: 'text' | 'image' | 'resource';
  content: string;
  mimeType?: string;
  metadata?: Record<string, any>;
}