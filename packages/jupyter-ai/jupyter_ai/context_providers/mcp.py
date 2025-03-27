"""
MCP Context Provider for Jupyter-AI

This module provides a context provider that can fetch resources from MCP servers.
The syntax is @server_name:resource_name.
"""

import logging
import re
from typing import List, Optional

from jupyter_ai.mcp import mcp_registry
from jupyter_ai.models import ListOptionsEntry
from jupyterlab_chat.models import Message

from .base import (
    BaseCommandContextProvider,
    ContextCommand,
    ContextProviderException,
    find_commands,
)

# Setup a more explicit logger
logger = logging.getLogger("jupyter_ai.context_providers.mcp")
logger.setLevel(logging.DEBUG)

MCP_CONTEXT_TEMPLATE = """
MCP Resource from server '{server}': {resource_name}
```
{content}
```
""".strip()


class McpContextProvider(BaseCommandContextProvider):
    id = "mcp"
    help = "Include content from an MCP server resource"
    requires_arg = True
    header = "Following are contents of referenced MCP resources:"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.debug("MCP Context Provider initialized")

    async def _init_registry(self):
        """Ensure the MCP registry is initialized"""
        if not hasattr(mcp_registry, "_initialized") or not mcp_registry._initialized:
            logger.debug("Initializing MCP registry")
            await mcp_registry.initialize()
        return mcp_registry._initialized

    def get_arg_options(self, arg_prefix: str) -> List[ListOptionsEntry]:
        """Get autocomplete options for MCP resources
        
        Format is: @mcp:server_name:resource_name
        """
        logger.debug(f"Getting autocomplete options for MCP with prefix: {arg_prefix}")
        
        # If no server name provided yet, list available servers
        if ":" not in arg_prefix:
            server_names = [s.name for s in mcp_registry.get_servers()]
            logger.debug(f"Available servers: {server_names}")
            return [
                self._make_arg_option(
                    arg=f"{server_name}:",
                    description=f"MCP Server: {server_name}",
                    is_complete=False,
                )
                for server_name in server_names
            ]
        
        # If server name provided but no resource name, list resources for that server
        server_name, _, resource_prefix = arg_prefix.partition(":")
        server = mcp_registry.get_server_by_name(server_name)
        
        if not server:
            logger.debug(f"Server not found: {server_name}")
            return []
            
        logger.debug(f"Resources for server {server_name}: {server.resources}")
        return [
            self._make_arg_option(
                arg=f"{server_name}:{resource['name']}",
                description=f"Resource: {resource['description'] or resource['name']}",
                is_complete=True,
            )
            for resource in server.resources
            if resource['name'].startswith(resource_prefix)
        ]

    async def _make_context_prompt(
        self, message: Message, commands: List[ContextCommand]
    ) -> str:
        """Create a context prompt from MCP resources"""
        logger.debug(f"Making context prompt for MCP resources. Commands: {commands}")
        
        # Make sure registry is initialized
        await self._init_registry()
        
        # Generate context for each command
        contexts = []
        for cmd in set(commands):
            try:
                context = await self._make_command_context(cmd)
                if context:
                    contexts.append(context)
            except ContextProviderException as e:
                # Re-raise exceptions to be handled by the chat handler
                raise e
            except Exception as e:
                logger.error(f"Error getting MCP resource: {e}")
                raise ContextProviderException(
                    f"Error getting MCP resource for `{cmd}`: {str(e)}"
                )
                
        if not contexts:
            return ""
            
        return self.header + "\n\n" + "\n\n".join(contexts)

    async def _make_command_context(self, command: ContextCommand) -> Optional[str]:
        """Get context for a specific MCP resource command"""
        arg = command.arg or ""
        if not arg:
            raise ContextProviderException(
                f"Invalid MCP resource reference: `{command}`. "
                f"Format must be @mcp:server_name:resource_name."
            )
            
        # Parse server_name:resource_name
        if ":" not in arg:
            raise ContextProviderException(
                f"Invalid MCP resource reference: `{command}`. "
                f"Format must be @mcp:server_name:resource_name."
            )
            
        server_name, _, resource_name = arg.partition(":")
        logger.debug(f"Fetching MCP resource: server={server_name}, resource={resource_name}")
        
        # Fetch the resource
        resource = await mcp_registry.get_resource(server_name, resource_name)
        if not resource:
            raise ContextProviderException(
                f"MCP resource not found: `{command}`. "
                f"Resource '{resource_name}' not found in server '{server_name}'."
            )
            
        # Only handle text resources for now
        if resource["type"] != "text":
            raise ContextProviderException(
                f"Unsupported MCP resource type: {resource['type']}. "
                f"Only text resources are supported for context."
            )
            
        return MCP_CONTEXT_TEMPLATE.format(
            server=server_name,
            resource_name=resource_name,
            content=resource["content"],
        )

    def _replace_command(self, command: ContextCommand) -> str:
        """Replace @mcp:server:resource with server:resource in the prompt"""
        arg = command.arg or ""
        return f"'{arg}'"