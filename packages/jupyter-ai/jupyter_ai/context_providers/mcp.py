"""
MCP Context Provider for Jupyter-AI

This module provides a context provider that can fetch resources from MCP servers.
The syntax is @server_name:resource_name.
"""

import logging
import re
from typing import List, Optional

from jupyter_ai.mcp import MCPServerRegistry
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

    def get_arg_options(self, arg_prefix: str) -> None:
        """Get autocomplete options for MCP resources
        
        Format is: @server_name:resource_name
        """

    async def _make_context_prompt(
        self, message: Message, commands: List[ContextCommand]
    ) -> str:
        """Create a context prompt from MCP resources"""
        
        # Generate context for each command
        contexts = []
        for cmd in set(commands):
            context = await self._make_command_context(cmd)
            if context:
                contexts.append(context)
  
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
        
        async with MCPServerRegistry.initialize_server(server_name) as client:
            resource = await client.read_resource(resource_name)
        if not resource:
            raise ContextProviderException(
                f"MCP resource not found: `{command}`. "
                f"Resource '{resource_name}' not found in server '{server_name}'."
            )
            
        return MCP_CONTEXT_TEMPLATE.format(
            server=server_name,
            resource_name=resource_name,
            content=resource.contents[0].text,
        )

    def _replace_command(self, command: ContextCommand) -> str:
        """Replace @mcp:server:resource with server:resource in the prompt"""
        arg = command.arg or ""
        return f"'{arg}'"