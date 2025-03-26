"""
MCP Server Registry for Jupyter-AI

This module provides functionality for discovering, connecting to, 
and managing MCP servers.
"""

from typing import Dict, List, Optional, Any, Union
import asyncio
import logging
import os
from pathlib import Path

from pydantic import BaseModel, Field

# Import MCP SDK - this will be a dependency we need to add
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    from mcp.types import Tool, Prompt, Resource
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    # Create stub classes for type checking when MCP is not installed
    class ClientSession:
        pass
    class StdioServerParameters:
        pass
    class Tool:
        pass
    class Prompt:
        pass
    class Resource:
        pass

import sys

# Setup a more explicit logger
logger = logging.getLogger("jupyter_ai.mcp")
logger.setLevel(logging.DEBUG)

# Configure a file handler for debugging
debug_log_path = "/tmp/jupyter_mcp_debug.log"
file_handler = logging.FileHandler(debug_log_path, mode='a')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Also add a stream handler to console
console_handler = logging.StreamHandler(stream=sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Log to let us know the logger is active
logger.info(f"MCP Registry logger initialized. Debug log at {debug_log_path}")

class McpServerInfo(BaseModel):
    """Information about an MCP server"""
    id: str
    name: str
    description: str = ""
    status: str = "available"
    capabilities: Dict[str, bool] = Field(default_factory=dict)
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    prompts: List[Dict[str, Any]] = Field(default_factory=list)
    resources: List[Dict[str, Any]] = Field(default_factory=list)
    connection_type: str = "stdio"  # stdio, sse, websocket
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    endpoint: Optional[str] = None


class McpRegistry:
    """Registry for MCP servers"""
    
    def __init__(self):
        self._servers: Dict[str, McpServerInfo] = {}
        self._sessions: Dict[str, ClientSession] = {}
        self._initialized = False
        
    async def initialize(self):
        """Initialize the registry and discover servers"""           
        if self._initialized:
            logger.info("MCP registry already initialized, skipping")
            return
        
        logger.debug(f"HAS_MCP = {HAS_MCP}")
        
        if not HAS_MCP:
            logger.warning("MCP Python SDK not installed. MCP functionality will be disabled.")
            self._initialized = True
            return

        logger.info("Initializing MCP registry")
        try:
            # Load server configuration
            await self._discover_servers()
            logger.info(f"MCP registry initialized with {len(self._servers)} servers")
            for server_id, server in self._servers.items():
                logger.info(f"  - {server.name} (ID: {server_id})")
        except Exception as e:
            logger.error(f"Error initializing MCP registry: {e}")
            # Still mark as initialized to avoid repeated attempts
            self._initialized = True
            return
            
        self._initialized = True
    
    async def _discover_servers(self):
        """Discover available MCP servers"""
        servers_to_discover = []
        
        # Check environment variables for MCP servers
        env_servers = os.environ.get("JUPYTER_MCP_SERVERS", "")
        logger.debug(f"MCP servers from environment: {env_servers}")
        if env_servers:
            # Split by comma while respecting paths that may contain colons
            for server_spec in env_servers.split(","):
                server_spec = server_spec.strip()
                logger.debug(f"Processing server spec: {server_spec}")
                
                # Handle the special format python:script.py for interpreter + script
                if ':' in server_spec:
                    first_part = server_spec.split(':', 1)[0]
                    if os.path.exists(first_part) and os.path.isfile(first_part):
                        logger.debug(f"Detected interpreter path: {first_part}")
                        # This is a Python interpreter followed by a script
                        parts = server_spec.split(':', 1)
                        interpreter = parts[0]
                        
                        if len(parts) > 1 and parts[1]:
                            # Get the script path and any arguments
                            script_parts = parts[1].strip().split()
                            script = script_parts[0]
                            script_args = script_parts[1:] if len(script_parts) > 1 else []
                            
                            logger.debug(f"Starting MCP server with: {interpreter} {script} {script_args}")
                            servers_to_discover.append({
                                "connection_type": "stdio",
                                "command": interpreter,
                                "args": [script] + script_args
                            })
                        else:
                            # Just an interpreter without a script
                            servers_to_discover.append({
                                "connection_type": "stdio",
                                "command": interpreter,
                                "args": []
                            })
                    elif server_spec.startswith("http:") or server_spec.startswith("https:"):
                        # This is an HTTP/HTTPS endpoint for SSE
                        logger.debug(f"Detected SSE endpoint: {server_spec}")
                        servers_to_discover.append({
                            "connection_type": "sse",
                            "endpoint": server_spec
                        })
                    else:
                        # Fall back to original behavior for non-file paths
                        parts = server_spec.split(":")
                        if len(parts) >= 2:
                            command, *args = parts
                            logger.debug(f"Using command format: {command} with args {args}")
                            servers_to_discover.append({
                                "connection_type": "stdio",
                                "command": command,
                                "args": args
                            })
                else:
                    # No colon - treat as a simple command or path
                    if os.path.exists(server_spec) and os.path.isfile(server_spec):
                        logger.debug(f"Detected executable path: {server_spec}")
                        servers_to_discover.append({
                            "connection_type": "stdio",
                            "command": server_spec,
                            "args": []
                        })
                    else:
                        logger.debug(f"Using as command name: {server_spec}")
                        servers_to_discover.append({
                            "connection_type": "stdio",
                            "command": server_spec,
                            "args": []
                        })
        
        # Check for local MCP servers in common locations
        local_paths = [
            # Try common local paths
            Path.home() / ".local" / "bin",
            Path.home() / ".mcp" / "servers",
            Path("/usr/local/bin"),
            Path("/opt/mcp/servers"),
        ]
        
        for path in local_paths:
            if path.exists() and path.is_dir():
                for file in path.glob("*-mcp-server"):
                    if file.is_file() and os.access(file, os.X_OK):
                        servers_to_discover.append({
                            "connection_type": "stdio",
                            "command": str(file),
                            "args": []
                        })

        logger.debug(f"MCP servers to discover: {servers_to_discover}")
        # Connect to servers and gather info
        for server_info in servers_to_discover:
            try:
                await self.register_server(
                    connection_type=server_info["connection_type"],
                    command=server_info["command"],
                    args=server_info["args"]
                )
                logger.info(f"Successfully registered MCP server: {server_info['command']}")
            except Exception as e:
                logger.error(f"Failed to register MCP server {server_info['command']}: {e}", exc_info=True)
    
    async def register_server(self, connection_type: str, command: str = None, 
                              args: List[str] = None, endpoint: str = None) -> Optional[str]:
        """Register an MCP server with the registry"""
        if not HAS_MCP:
            logger.warning("Cannot register MCP server: MCP SDK not installed")
            return None
            
        server_params = None
        transport = None
        server_id = None
        
        try:
            if connection_type == "stdio":
                if not command:
                    raise ValueError("Command is required for stdio connection")
                
                server_params = StdioServerParameters(
                    command=command,
                    args=args or []
                )
                logger.info(f"Connecting to MCP server with command: {command} {' '.join(args or [])}")
                logger.debug(f"Server parameters: {server_params}")
                
                # Handle async context manager correctly
                context_manager = stdio_client(server_params)
                logger.debug("Created stdio client context manager")
                
                try:
                    transport = await context_manager.__aenter__()
                    logger.debug("Entered stdio client context")
                except Exception as e:
                    logger.error(f"Failed to enter stdio client context: {e}")
                    raise
            elif connection_type == "sse":
                if not endpoint:
                    raise ValueError("Endpoint is required for SSE connection")
                
                logger.info(f"Connecting to MCP server with SSE endpoint: {endpoint}")
                
                # Handle async context manager correctly
                context_manager = sse_client(endpoint)
                logger.debug("Created SSE client context manager")
                
                try:
                    transport = await context_manager.__aenter__()
                    logger.debug("Entered SSE client context")
                except Exception as e:
                    logger.error(f"Failed to enter SSE client context: {e}")
                    raise
            else:
                raise ValueError(f"Unsupported connection type: {connection_type}")
            
            # Create session
            logger.debug("Creating client session")
            from datetime import timedelta
            seconds = timedelta(seconds=5)
            session = ClientSession(*transport, read_timeout_seconds=seconds)
            
            # Initialize the session with a timeout
            logger.debug("Initializing session with timeout")
            try:
                # Import asyncio for timeout functionality
                import asyncio
                
                # Set a timeout of 5 seconds for initialization
                init_task = asyncio.create_task(session.initialize())
                init_result = await asyncio.wait_for(init_task, timeout=5.0)
                
                # Generate a unique ID for this server
                server_name = init_result.serverInfo.name
                server_id = f"{server_name}-{id(session)}"
                
                logger.debug(f"Successfully initialized session for server {server_name}")
            except asyncio.TimeoutError:
                logger.error("Timeout while initializing MCP session")
                # Clean up if needed
                if 'context_manager' in locals() and hasattr(context_manager, '__aexit__'):
                    try:
                        await context_manager.__aexit__(None, None, None)
                    except Exception as exit_error:
                        logger.error(f"Error cleaning up MCP transport after timeout: {exit_error}")
                raise TimeoutError("MCP server initialization timed out")
            
            # Register the server
            logger.debug("Register server")
            server_info = McpServerInfo(
                id=server_id,
                name=server_name,
                description=init_result.instructions or f"MCP Server: {server_name}",
                status="available",
                capabilities={
                    "prompts": init_result.capabilities.prompts is not None,
                    "resources": init_result.capabilities.resources is not None,
                    "tools": init_result.capabilities.tools is not None,
                },
                connection_type=connection_type,
                command=command,
                args=args or [],
                endpoint=endpoint
            )
            
            # Store session and server info
            self._sessions[server_id] = session
            self._servers[server_id] = server_info
            
            # Fetch tools and prompts
            logger.debug("Fetching capabilites")
            await self._fetch_server_capabilities(server_id)
            
            logger.info(f"Registered MCP server: {server_name}")
            return server_id
        
        except Exception as e:
            logger.error(f"Error registering MCP server: {e}")
            
            # Clean up if needed
            if 'context_manager' in locals() and hasattr(context_manager, '__aexit__'):
                try:
                    await context_manager.__aexit__(type(e), e, e.__traceback__)
                except Exception as exit_error:
                    logger.error(f"Error cleaning up MCP transport: {exit_error}")
            
            return None
    
    async def _fetch_server_capabilities(self, server_id: str):
        """Fetch tools and prompts from an MCP server"""
        session = self._sessions.get(server_id)
        server_info = self._servers.get(server_id)
        
        if not session or not server_info:
            return
        
        # Fetch tools if supported
        if server_info.capabilities.get("tools"):
            try:
                tools_response = await session.list_tools()
                tools = []
                
                # Extract tools from response
                for item in tools_response:
                    if isinstance(item, tuple) and item[0] == "tools":
                        for tool in item[1]:
                            tools.append({
                                "name": tool.name,
                                "description": tool.description,
                                "inputSchema": tool.inputSchema
                            })
                
                server_info.tools = tools
            except Exception as e:
                logger.warning(f"Failed to fetch tools from server {server_info.name}: {e}")
        
        # Fetch prompts if supported
        if server_info.capabilities.get("prompts"):
            try:
                prompts_response = await session.list_prompts()
                prompts = []
                
                # Extract prompts from response
                for prompt in prompts_response.prompts:
                    prompts.append({
                        "name": prompt.name,
                        "description": prompt.description,
                        "arguments": [
                            {"name": arg.name, "description": arg.description, "required": arg.required}
                            for arg in (prompt.arguments or [])
                        ]
                    })
                
                server_info.prompts = prompts
            except Exception as e:
                logger.warning(f"Failed to fetch prompts from server {server_info.name}: {e}")
                
        # Fetch resources if supported
        if server_info.capabilities.get("resources"):
            try:
                resources_response = await session.list_resources()
                resources = []
                
                # Extract resources from response
                for resource in resources_response.resources:
                    resources.append({
                        "uri": str(resource.uri),
                        "name": resource.name,
                        "description": resource.description
                    })
                
                server_info.resources = resources
            except Exception as e:
                logger.warning(f"Failed to fetch resources from server {server_info.name}: {e}")
    
    def get_servers(self) -> List[McpServerInfo]:
        """Get all registered servers"""
        return list(self._servers.values())
    
    def get_server(self, server_id: str) -> Optional[McpServerInfo]:
        """Get server by ID"""
        return self._servers.get(server_id)
    
    def get_server_by_name(self, name: str) -> Optional[McpServerInfo]:
        """Get server by name"""
        for server in self._servers.values():
            if server.name.lower() == name.lower():
                return server
        return None
    
    async def get_session(self, server_id: str) -> Optional[ClientSession]:
        """Get MCP client session for a server"""
        if not HAS_MCP:
            return None
            
        session = self._sessions.get(server_id)
        
        # Reconnect if needed
        if session is None:
            server = self._servers.get(server_id)
            if server:
                new_server_id = await self.register_server(
                    connection_type=server.connection_type,
                    command=server.command,
                    args=server.args,
                    endpoint=server.endpoint
                )
                if new_server_id:
                    session = self._sessions.get(new_server_id)
        
        return session
    
    async def execute_command(self, server_name: str, command: str = "", arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a command on an MCP server with optional arguments"""
        if not HAS_MCP:
            return {
                "type": "text",
                "content": "Error: MCP support is not available. Please install the MCP Python SDK."
            }
            
        logger.debug(f"Executing MCP command: server={server_name}, command={command}, arguments={arguments}")
        
        # If no arguments provided, initialize an empty dict
        if arguments is None:
            arguments = {}
            
        server = self.get_server_by_name(server_name)
        if not server:
            available_servers = [s.name for s in self.get_servers()]
            servers_list = ", ".join(available_servers) if available_servers else "None"
            return {
                "type": "text",
                "content": f"Error: MCP server '{server_name}' not found or not available.\n\nAvailable servers: {servers_list}"
            }
        
        # Get session with retry on failure
        session = await self.get_session(server.id)
        if not session:
            return {
                "type": "text",
                "content": f"Error: Failed to connect to MCP server '{server_name}'. The server may be unavailable."
            }
        
        try:
            # If a specific command is provided, use it
            if command:
                # Try as prompt first
                if server.capabilities.get("prompts"):
                    for prompt in server.prompts:
                        if prompt["name"] == command:
                            # Get prompt with provided arguments or default
                            prompt_result = await session.get_prompt(
                                command, 
                                arguments=arguments or {"input": ""}
                            )
                            
                            # Format prompt result
                            text_content = ""
                            for message in prompt_result.messages:
                                if hasattr(message.content, "text"):
                                    text_content += message.content.text + "\n"
                            
                            return {
                                "type": "text",
                                "content": text_content.strip()
                            }
                
                # Try as tool
                if server.capabilities.get("tools"):
                    for tool in server.tools:
                        if tool["name"] == command:
                            # Call tool with provided arguments or default
                            tool_result = await session.call_tool(
                                command, 
                                arguments=arguments or {"input": ""}
                            )
                            
                            # Format tool result
                            if hasattr(tool_result.content[0], "text"):
                                return {
                                    "type": "text",
                                    "content": tool_result.content[0].text
                                }
                            elif hasattr(tool_result.content[0], "data"):
                                return {
                                    "type": "image",
                                    "content": tool_result.content[0].data,
                                    "mimeType": tool_result.content[0].mimeType
                                }
                            elif hasattr(tool_result.content[0], "resource"):
                                return {
                                    "type": "resource",
                                    "content": tool_result.content[0].resource.text,
                                    "mimeType": tool_result.content[0].resource.mimeType,
                                    "metadata": {"uri": tool_result.content[0].resource.uri}
                                }
            
            # No specific command or command not found, try server name as command
            # Try to get a prompt with the server name
            if server.capabilities.get("prompts"):
                try:
                    prompt_result = await session.get_prompt(
                        server_name, 
                        arguments=arguments or {"input": ""}
                    )
                    
                    # Format prompt result
                    text_content = ""
                    for message in prompt_result.messages:
                        if hasattr(message.content, "text"):
                            text_content += message.content.text + "\n"
                    
                    return {
                        "type": "text",
                        "content": text_content.strip()
                    }
                except Exception:
                    # If prompt not found, continue to try as tool
                    pass
            
            # Try to call a tool with the server name
            if server.capabilities.get("tools"):
                try:
                    tool_result = await session.call_tool(
                        server_name, 
                        arguments=arguments or {"input": ""}
                    )
                    
                    # Format tool result
                    if tool_result.content and len(tool_result.content) > 0:
                        if hasattr(tool_result.content[0], "text"):
                            return {
                                "type": "text",
                                "content": tool_result.content[0].text
                            }
                        elif hasattr(tool_result.content[0], "data"):
                            return {
                                "type": "image",
                                "content": tool_result.content[0].data,
                                "mimeType": tool_result.content[0].mimeType
                            }
                        elif hasattr(tool_result.content[0], "resource"):
                            return {
                                "type": "resource",
                                "content": tool_result.content[0].resource.text,
                                "mimeType": tool_result.content[0].resource.mimeType,
                                "metadata": {"uri": tool_result.content[0].resource.uri}
                            }
                except Exception:
                    # If tool call fails, show appropriate error
                    pass
            
            # If we get here, we couldn't find a matching command
            available_commands = []
            if server.capabilities.get("prompts"):
                available_commands.extend([p["name"] for p in server.prompts])
            if server.capabilities.get("tools"):
                available_commands.extend([t["name"] for t in server.tools])
                
            if available_commands:
                commands_list = ", ".join(available_commands)
                return {
                    "type": "text",
                    "content": f"Error: No matching prompt or tool found for '{command or server_name}' in server '{server.name}'.\n\nAvailable commands: {commands_list}"
                }
            else:
                return {
                    "type": "text",
                    "content": f"Error: Server '{server.name}' has no available commands."
                }
            
        except Exception as e:
            return {
                "type": "text",
                "content": f"Error executing MCP command: {str(e)}"
            }
    
    async def shutdown(self):
        """Shut down all server connections"""
        if not HAS_MCP:
            return
            
        for server_id, session in self._sessions.items():
            try:
                if hasattr(session, 'aclose'):
                    await session.aclose()
                elif hasattr(session, 'close'):
                    await session.close()
                elif hasattr(session, '__aexit__'):
                    await session.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing MCP session for {server_id}: {e}")
        
        self._sessions.clear()
        self._servers.clear()
        self._initialized = False


# Create a singleton registry instance
mcp_registry = McpRegistry()