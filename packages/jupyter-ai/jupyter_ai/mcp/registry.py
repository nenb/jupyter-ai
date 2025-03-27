"""
MCP Server Registry for Jupyter-AI

This module provides functionality for discovering, connecting to, 
and managing MCP servers.
"""

from typing import Dict, List, Optional, Any, Union
import asyncio
import logging
import os
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from pydantic import BaseModel, Field

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.types import Tool, Prompt, Resource
HAS_MCP = True

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

class McpServerYamlConfig(BaseModel):
    """YAML configuration for an MCP server"""
    command: str
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    description: Optional[str] = None
    connection_type: str = "stdio"
    endpoint: Optional[str] = None

class McpYamlConfig(BaseModel):
    """YAML configuration for MCP settings"""
    servers: Dict[str, McpServerYamlConfig]

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
    connection_type: str = "stdio"
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    endpoint: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)


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
    
    def _load_yaml_config(self):
        """Load MCP server configuration from YAML files"""
        if not HAS_YAML:
            logger.warning("YAML support not available. Please install PyYAML to use YAML configuration files.")
            return []
        
        servers_from_yaml = []
        
        # Try common config locations
        config_paths = [
            # Current directory
            Path.cwd() / "jupyter_mcp_config.yml",
            Path.cwd() / "jupyter_mcp_config.yaml",
            # User's home directory
            Path.home() / ".jupyter" / "jupyter_mcp_config.yml",
            Path.home() / ".jupyter" / "jupyter_mcp_config.yaml",
            Path.home() / ".config" / "jupyter" / "jupyter_mcp_config.yml",
            Path.home() / ".config" / "jupyter" / "jupyter_mcp_config.yaml",
            # System-wide configuration
            Path("/etc/jupyter/jupyter_mcp_config.yml"),
            Path("/etc/jupyter/jupyter_mcp_config.yaml"),
        ]
        
        # Environment variable can specify a config file
        env_config = os.environ.get("JUPYTER_MCP_CONFIG")
        if env_config:
            config_paths.insert(0, Path(env_config))
            
        # Try each config path
        for config_path in config_paths:
            if config_path.exists() and config_path.is_file():
                logger.info(f"Loading MCP configuration from {config_path}")
                try:
                    with open(config_path, 'r') as f:
                        config_data = yaml.safe_load(f)
                        
                    # Check if config has the expected structure
                    if not isinstance(config_data, dict) or "mcp" not in config_data:
                        logger.warning(f"Invalid MCP configuration in {config_path}. Missing 'mcp' key.")
                        continue
                        
                    mcp_config = config_data.get("mcp", {})
                    if not isinstance(mcp_config, dict) or "servers" not in mcp_config:
                        logger.warning(f"Invalid MCP configuration in {config_path}. Missing 'mcp.servers' key.")
                        continue
                    
                    # Parse server configuration
                    servers = mcp_config.get("servers", {})
                    for server_name, server_config in servers.items():
                        try:
                            # Validate using Pydantic model
                            if isinstance(server_config, dict):
                                yaml_config = McpServerYamlConfig(**server_config)
                                # Convert to dictionary for register_server
                                server_dict = {
                                    "name": server_name,
                                    "connection_type": yaml_config.connection_type,
                                    "command": yaml_config.command,
                                    "args": yaml_config.args,
                                    "endpoint": yaml_config.endpoint,
                                    "env": yaml_config.env,
                                    "description": yaml_config.description or f"MCP Server: {server_name}"
                                }
                                servers_from_yaml.append(server_dict)
                                logger.info(f"Loaded server configuration for {server_name}")
                            else:
                                logger.warning(f"Invalid server configuration for {server_name}. Expected dictionary.")
                        except Exception as e:
                            logger.warning(f"Error parsing server configuration for {server_name}: {e}")
                except Exception as e:
                    logger.warning(f"Error loading YAML configuration from {config_path}: {e}")
        
        return servers_from_yaml
                
    async def _discover_servers(self):
        """Discover available MCP servers"""
        servers_to_discover = []
        
        # Load servers from YAML configuration
        yaml_servers = self._load_yaml_config()
        if yaml_servers:
            servers_to_discover.extend(yaml_servers)

        logger.debug(f"MCP servers to discover: {servers_to_discover}")
        # Connect to servers and gather info
        for server_info in servers_to_discover:
            try:
                # Handle name if available (from YAML config)
                name = server_info.get("name")
                description = server_info.get("description")
                env_vars = server_info.get("env", {})
                
                await self.register_server(
                    connection_type=server_info["connection_type"],
                    command=server_info.get("command"),
                    args=server_info.get("args", []),
                    endpoint=server_info.get("endpoint"),
                    env_vars=env_vars,
                    name=name,
                    description=description
                )
                
                server_id = server_info.get('command', server_info.get('endpoint'))
                if name:
                    server_id = f"{name} ({server_id})"
                    
                logger.info(f"Successfully registered MCP server: {server_id}")
            except Exception as e:
                server_id = server_info.get('command', server_info.get('endpoint'))
                if server_info.get("name"):
                    server_id = f"{server_info.get('name')} ({server_id})"
                    
                logger.error(f"Failed to register MCP server {server_id}: {e}", exc_info=True)
    
    async def register_server(self, connection_type: str, command: str = None, 
                              args: List[str] = None, endpoint: str = None,
                              env_vars: Dict[str, str] = None, name: str = None, 
                              description: str = None) -> Optional[str]:
        """Register an MCP server with the registry"""
            
        # Initialize env_vars if None
        if env_vars is None:
            env_vars = {}
            
        server_id = None
        
        # Import asyncio for timeout functionality
        import asyncio
        from datetime import timedelta
        
        try:
            # Set up the connection based on connection type
            if connection_type == "stdio":
                if not command:
                    raise ValueError("Command is required for stdio connection")
                
                # Create stdio server parameters with environment variables
                server_params = StdioServerParameters(
                    command=command,
                    args=args or [],
                    env=env_vars
                )
                logger.info(f"Connecting to MCP server with command: {command} {' '.join(args or [])}")
                logger.debug(f"Server parameters: {server_params}")
                
                # Use stdio_client as a proper context manager
                async with stdio_client(server_params) as transport:
                    logger.debug("Successfully entered stdio client context")
                    
                    # Create session with read timeout
                    read_timeout = timedelta(seconds=5)
                    async with ClientSession(*transport, read_timeout_seconds=read_timeout) as session:
                        logger.debug("Created client session and entered session context")
                        
                        # Initialize session with timeout
                        logger.debug("Initializing session with timeout")
                        try:
                            # Set a timeout of 5 seconds for initialization
                            init_result = await asyncio.wait_for(session.initialize(), timeout=5.0)
                            
                            # Generate a unique ID for this server
                            server_name = init_result.serverInfo.name
                            server_id = f"{server_name}-{id(session)}"
                            
                            logger.debug(f"Successfully initialized session for server {server_name}")
                            
                            # Register the server
                            logger.debug("Registering server")
                            server_info = McpServerInfo(
                                id=server_id,
                                # Use custom name if provided, otherwise server's default name
                                name=name or server_name,
                                # Use custom description if provided, otherwise server's instructions or default
                                description=description or init_result.instructions or f"MCP Server: {server_name}",
                                status="available",
                                capabilities={
                                    "prompts": init_result.capabilities.prompts is not None,
                                    "resources": init_result.capabilities.resources is not None,
                                    "tools": init_result.capabilities.tools is not None,
                                },
                                connection_type=connection_type,
                                command=command,
                                args=args or [],
                                endpoint=endpoint,
                                # Include environment variables
                                env=env_vars or {}
                            )
                            
                            # Store session and server info - will keep session alive
                            self._sessions[server_id] = session
                            self._servers[server_id] = server_info
                            
                            logger.debug("Fetching capabilities")
                            await self._fetch_server_capabilities(server_id)
                            
                            logger.info(f"Registered MCP server: {server_name}")
                            return server_id
                            
                        except asyncio.TimeoutError:
                            logger.error("Timeout while initializing MCP session")
                            raise TimeoutError("MCP server initialization timed out")
                
            elif connection_type == "sse":
                if not endpoint:
                    raise ValueError("Endpoint is required for SSE connection")
                
                logger.info(f"Connecting to MCP server with SSE endpoint: {endpoint}")
                
                # Use sse_client as a proper context manager
                async with sse_client(endpoint) as transport:
                    logger.debug("Successfully entered SSE client context")
                    
                    # Create session with read timeout
                    read_timeout = timedelta(seconds=5)
                    async with ClientSession(*transport, read_timeout_seconds=read_timeout) as session:
                        logger.debug("Created client session and entered session context")
                        
                        # Initialize session with timeout
                        logger.debug("Initializing session with timeout")
                        try:
                            # Set a timeout of 5 seconds for initialization
                            init_result = await asyncio.wait_for(session.initialize(), timeout=5.0)
                            
                            # Generate a unique ID for this server
                            server_name = init_result.serverInfo.name
                            server_id = f"{server_name}-{id(session)}"
                            
                            logger.debug(f"Successfully initialized session for server {server_name}")
                            
                            # Register the server
                            logger.debug("Registering server")
                            server_info = McpServerInfo(
                                id=server_id,
                                # Use custom name if provided, otherwise server's default name
                                name=name or server_name,
                                # Use custom description if provided, otherwise server's instructions or default
                                description=description or init_result.instructions or f"MCP Server: {server_name}",
                                status="available",
                                capabilities={
                                    "prompts": init_result.capabilities.prompts is not None,
                                    "resources": init_result.capabilities.resources is not None,
                                    "tools": init_result.capabilities.tools is not None,
                                },
                                connection_type=connection_type,
                                command=command,
                                args=args or [],
                                endpoint=endpoint,
                                # Include environment variables
                                env=env_vars or {}
                            )
                            
                            # Store session and server info - will keep session alive
                            self._sessions[server_id] = session
                            self._servers[server_id] = server_info
                            
                            logger.debug("Fetching capabilities")
                            await self._fetch_server_capabilities(server_id)
                            
                            logger.info(f"Registered MCP server: {server_name}")
                            return server_id
                            
                        except asyncio.TimeoutError:
                            logger.error("Timeout while initializing MCP session")
                            raise TimeoutError("MCP server initialization timed out")
            
            else:
                raise ValueError(f"Unsupported connection type: {connection_type}")
            
        except Exception as e:
            logger.error(f"Error registering MCP server: {e}")
            return None
    
    async def _fetch_server_capabilities(self, server_id: str):
        session = self._sessions.get(server_id)
        server_info = self._servers.get(server_id)
        
        if not session or not server_info:
            return
                
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
                    endpoint=server.endpoint,
                    env_vars=server.env,
                    name=server.name,
                    description=server.description
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
                    logger.debug(f"Tools are {server.tools}, session: {session}")
                    for tool in server.tools:
                        logger.debug(f"Tool is {tool['name']}, command is {command}, equal {tool["name"] == command}")
                        if tool["name"] == command:
                            # Special case for greeting commands
                            if command.lower() == "greet" and not arguments:
                                # For the greet command without arguments, make sure it works
                                logger.debug(f"Special case: greet command without arguments")
                                tool_result = await session.call_tool(
                                    command,
                                    arguments={"name": "User"}  # Default greeting name
                                )
                            else:
                                # Call tool with provided arguments or default
                                tool_result = await session.call_tool(
                                    command, 
                                    arguments=arguments
                                )
                            logger.debug(f"Greeting: {tool_result}")
                            # Format tool result
                            if hasattr(tool_result.content[0], "text"):
                                logger.debug(f"Greeting: {tool_result.content[0].text}")
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
            
    async def get_resource(self, server_name: str, resource_name: str) -> Optional[Dict[str, Any]]:
        """Get a resource from an MCP server
        
        Args:
            server_name: Name of the MCP server
            resource_name: Name of the resource to fetch
            
        Returns:
            A dictionary with the resource content and metadata, or None if not found
        """
        if not HAS_MCP:
            logger.error("MCP support is not available. Please install the MCP Python SDK.")
            return None
            
        logger.debug(f"Fetching MCP resource: server={server_name}, resource={resource_name}")
            
        server = self.get_server_by_name(server_name)
        if not server:
            logger.error(f"MCP server '{server_name}' not found or not available.")
            return None
        
        # Check if server supports resources
        if not server.capabilities.get("resources"):
            logger.error(f"MCP server '{server_name}' does not support resources.")
            return None
            
        # Get session with retry on failure
        session = await self.get_session(server.id)
        if not session:
            logger.error(f"Failed to connect to MCP server '{server_name}'. The server may be unavailable.")
            return None
        
        try:
            # Find the resource URI
            resource_uri = None
            for resource in server.resources:
                if resource["name"] == resource_name:
                    resource_uri = resource["uri"]
                    break
                    
            if not resource_uri:
                logger.error(f"Resource '{resource_name}' not found in server '{server_name}'.")
                return None
                
            # Fetch the resource
            logger.debug(f"Fetching resource with URI: {resource_uri}")
            resource_result = await session.get_resource(resource_uri)
            
            # Format resource result
            if resource_result.text:
                return {
                    "type": "text",
                    "content": resource_result.text,
                    "mime_type": resource_result.mimeType
                }
            elif resource_result.data:
                return {
                    "type": "data",
                    "content": resource_result.data,
                    "mime_type": resource_result.mimeType
                }
            else:
                logger.error(f"Resource '{resource_name}' returned empty content.")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching MCP resource: {str(e)}")
            return None
    
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