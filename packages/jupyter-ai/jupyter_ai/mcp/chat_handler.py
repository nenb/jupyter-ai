"""
MCP Chat Handler for Jupyter-AI

This module provides a chat handler for MCP slash commands.
"""

from typing import Dict, List, Any, Optional
import logging
import shlex
import argparse

from jupyter_ai.chat_handlers.base import BaseChatHandler, SlashCommandRoutingType
from jupyterlab_chat.models import Message
from .registry import mcp_registry

logger = logging.getLogger(__name__)

class McpChatHandler(BaseChatHandler):
    """Handler for MCP commands in the chat interface"""

    id = "mcp"
    name = "MCP"
    help = "Interact with MCP servers to get context and execute commands"
    routing_type = SlashCommandRoutingType(slash_id="mcp")
    uses_llm = False  # This handler doesn't use the LLM directly

    async def process_message(self, human_message: Message):
        """Process an MCP command message"""
        # Parse the command
        tokens = shlex.split(human_message.body)
        if len(tokens) < 2:
            # Not enough arguments
            self.reply("Usage: /mcp <server_name> [command] [arguments]", human_message)
            return

        # Extract components
        server_name = tokens[1]
        command = tokens[2] if len(tokens) > 2 else ""
        arguments = " ".join(tokens[3:]) if len(tokens) > 3 else ""

        # Execute the command
        result = await mcp_registry.execute_command(
            server_name=server_name,
            command=command,
            arguments=arguments
        )

        # Add result to context for the LLM
        context = []
        if result["type"] == "text":
            context.append({
                "type": "mcp_result",
                "server": server_name,
                "content": result["content"]
            })

        # Reply with the result
        self.reply(result["content"], human_message)

        # Return context for LLM
        return {"context": context}

    async def handle_exc(self, e: Exception, human_message: Message):
        """Handle exceptions from MCP command execution"""
        logger.error(f"Error handling MCP command: {e}")
        self.reply(f"Error executing MCP command: {str(e)}", human_message)


class McpServerChatHandler(BaseChatHandler):
    """Handler for direct MCP server commands in the chat interface"""

    id = "mcp_server"
    name = "MCP Server"
    help = "Access MCP server capabilities"
    routing_type = SlashCommandRoutingType()  # Dynamic slash ID
    uses_llm = False  # This handler doesn't use the LLM directly

    async def can_handle(self, command: str) -> bool:
        """Check if this handler can process the command"""
        # Ensure registry is initialized
        if not mcp_registry._initialized:
            await mcp_registry.initialize()
        
        # Strip the leading slash
        if command.startswith('/'):
            command = command[1:]
            
        # Check if any server matches this command
        server = mcp_registry.get_server_by_name(command)
        return server is not None

    async def process_message(self, human_message: Message):
        """Process a direct MCP server command"""
        # Parse the command
        tokens = shlex.split(human_message.body)
        server_name = tokens[0][1:]  # Remove leading /
        arguments = " ".join(tokens[1:]) if len(tokens) > 1 else ""

        # Execute the command
        result = await mcp_registry.execute_command(
            server_name=server_name,
            arguments=arguments
        )

        # Add result to context for the LLM
        context = []
        if result["type"] == "text":
            context.append({
                "type": "mcp_result",
                "server": server_name,
                "content": result["content"]
            })

        # Reply with the result
        self.reply(result["content"], human_message)

        # Return context for LLM
        return {"context": context}

    async def handle_exc(self, e: Exception, human_message: Message):
        """Handle exceptions from MCP command execution"""
        logger.error(f"Error handling MCP server command: {e}")
        self.reply(f"Error executing MCP command: {str(e)}", human_message)