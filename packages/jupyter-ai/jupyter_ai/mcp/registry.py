"""
TAKEN FROM: https://github.com/lastmile-ai/mcp-agent/blob/main/src/mcp_agent/mcp_server_registry.py

This module defines a `ServerRegistry` class for managing MCP server configurations
and initialization logic.

The class loads server configurations from a YAML file,
supports dynamic registration of initialization hooks, and provides methods for
server initialization.
"""

from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Dict, AsyncGenerator, Any
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import (
    StdioServerParameters,
    stdio_client,
    get_default_environment,
)
from mcp.client.sse import sse_client
import yaml
from pydantic import BaseModel, Field

class McpServerYamlConfig(BaseModel):
    """YAML configuration for an MCP server"""
    command: str
    args: list[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    description: str | None = None
    transport: str = "stdio"
    endpoint: str | None = None


class ServerRegistry:
    """
    A registry for managing server configurations and initialization logic.

    The `ServerRegistry` class is responsible for loading server configurations
    from a YAML file, registering initialization hooks, initializing servers,
    and executing post-initialization hooks dynamically.

    Attributes:
        registry (Dict[str, MCPServerSettings]): Loaded server configurations.
    """

    def __init__(self):
        """
        Initialize the ServerRegistry with a configuration file.

        """
        self.registry = (
            self.load_registry_from_file()
        )

    def load_registry_from_file(
        self,
    ) -> Dict[str, Any]:

        servers_from_yaml = {}

        config_path = Path.cwd() / "jupyter_mcp_config.yaml"

        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)

        mcp_config = config_data.get("mcp", {})

        # Parse server configuration
        servers = mcp_config.get("servers", {})
        for server_name, server_config in servers.items():
            yaml_config = McpServerYamlConfig(**server_config)
            # Convert to dictionary for register_server
            server_dict = {
                "name": server_name,
                "transport": yaml_config.transport,
                "command": yaml_config.command,
                "args": yaml_config.args,
                "endpoint": yaml_config.endpoint,
                "env": yaml_config.env,
                "description": yaml_config.description or f"MCP Server: {server_name}"
            }
            servers_from_yaml[server_name] = server_dict

        return servers_from_yaml

    @asynccontextmanager
    async def start_server(
        self,
        server_name: str,
    ) -> AsyncGenerator[ClientSession, None]:
        """
        Starts the server process based on its configuration. To initialize, call initialize_server

        Args:
            server_name (str): The name of the server to initialize.

        Returns:
            StdioServerParameters: The server parameters for stdio transport.

        Raises:
            ValueError: If the server is not found or has an unsupported transport.
        """
        config = self.registry[server_name]

        read_timeout_seconds = (
            timedelta(seconds=5)
        )

        if config["transport"] == "stdio":
            if not config["command"] or not config["args"]:
                raise ValueError(
                    f"Command and args are required for stdio transport: {server_name}"
                )

            server_params = StdioServerParameters(
                command=config["command"],
                args=config["args"],
                env={**get_default_environment(), **(config["env"] or {})},
            )

            async with stdio_client(server_params) as (read_stream, write_stream):
                session = ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds,
                )
                async with session:
                    yield session


        elif config["transport"] == "sse":
            if not config["url"]:
                raise ValueError(f"URL is required for SSE transport: {server_name}")

            # Use sse_client to get the read and write streams
            async with sse_client(config["url"]) as (read_stream, write_stream):
                session = ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds,
                )
                async with session:
                    yield session

        # Unsupported transport
        else:
            raise ValueError(f"Unsupported transport: {config['transport']}")

    @asynccontextmanager
    async def initialize_server(
        self,
        server_name: str,
    ) -> AsyncGenerator[ClientSession, None]:
        """
        Initialize a server based on its configuration.
        After initialization, also calls any registered or provided initialization hook for the server.

        Args:
            server_name (str): The name of the server to initialize.

        Returns:
            StdioServerParameters: The server parameters for stdio transport.

        Raises:
            ValueError: If the server is not found or has an unsupported transport.
        """

        if server_name not in self.registry:
            raise ValueError(f"Server '{server_name}' not found in registry.")

        async with self.start_server(
            server_name,
        ) as session:
            await session.initialize()

            yield session

MCPServerRegistry = ServerRegistry()