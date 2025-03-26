"""
MCP Chat Handler for Jupyter-AI

This module provides a chat handler for MCP slash commands.
"""

from typing import Dict, List, Any, Optional, Tuple
import logging
import shlex
import json
import re
import argparse

from jupyter_ai.chat_handlers.base import BaseChatHandler, SlashCommandRoutingType
from jupyterlab_chat.models import Message
from .registry import mcp_registry

logger = logging.getLogger("jupyter_ai.mcp.chat_handler")

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
        try:
            tokens = shlex.split(human_message.body)
        except ValueError as e:
            # Handle quoting errors
            self.reply(f"Error parsing command: {str(e)}", human_message)
            return

        if len(tokens) < 2:
            # Not enough arguments
            self.reply("Usage: /mcp <server_name> [command] [arguments]", human_message)
            return

        # Extract components
        server_name = tokens[1]
        
        # Get available servers to display in case of error
        servers = []
        if mcp_registry._initialized:
            servers = [s.name for s in mcp_registry.get_servers()]
        
        # If no servers available, display useful message
        if not servers:
            self.reply("No MCP servers available. Please configure MCP servers and try again.", human_message)
            return
            
        # Check if the specified server exists
        server = mcp_registry.get_server_by_name(server_name)
        if not server:
            servers_list = ", ".join(servers) if servers else "None"
            self.reply(f"Error: MCP server '{server_name}' not found.\n\nAvailable servers: {servers_list}", human_message)
            return
            
        # Parse command and arguments
        command = ""
        args = {}
        
        if len(tokens) > 2:
            command = tokens[2]
            
            # Process any key=value pairs from remaining tokens
            arg_tokens = tokens[3:]
            for arg in arg_tokens:
                # Match key=value pattern
                match = re.match(r'^([^=]+)=(.*)$', arg)
                if match:
                    key, value = match.groups()
                    # Try to parse as JSON for numbers, booleans, etc.
                    try:
                        value = json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        # If not valid JSON, keep as string
                        pass
                    args[key] = value
        
        logger.debug(f"MCP command: server={server_name}, command={command}, args={args}")

        # Execute the command with arguments
        result = await mcp_registry.execute_command(
            server_name=server_name,
            command=command,
            arguments=args
        )

        # Add result to context for the LLM
        context = []
        if result["type"] == "text":
            context.append({
                "type": "mcp_result",
                "server": server_name,
                "command": command,
                "content": result["content"]
            })

        # Create a message with MCP-specific metadata
        message_text = result["content"]
        message_metadata = {
            "mcp_result": {
                "server": server_name,
                "command": command,
                "arguments": args,
                "type": result["type"],
                "metadata": result.get("metadata", {})
            }
        }
        
        # Reply with the result and metadata
        self.reply(message_text, human_message, metadata=message_metadata)

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
            try:
                await mcp_registry.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize MCP registry: {e}")
                return False
        
        # Strip the leading slash
        if command.startswith('/'):
            command = command[1:]
            
        # Check if any server matches this command
        server = mcp_registry.get_server_by_name(command)
        return server is not None

    async def process_message(self, human_message: Message):
        """Process a direct MCP server command"""
        try:
            # Parse the command
            tokens = shlex.split(human_message.body)
            server_name = tokens[0][1:]  # Remove leading /
            
            # Process additional arguments if provided
            args = {}
            if len(tokens) > 1:
                arg_tokens = tokens[1:]
                for arg in arg_tokens:
                    # Match key=value pattern
                    match = re.match(r'^([^=]+)=(.*)$', arg)
                    if match:
                        key, value = match.groups()
                        # Try to parse as JSON for numbers, booleans, etc.
                        try:
                            value = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            # If not valid JSON, keep as string
                            pass
                        args[key] = value
            
            logger.debug(f"Direct MCP server command: server={server_name}, args={args}")

            # Execute the command with arguments if provided
            if args:
                result = await mcp_registry.execute_command(
                    server_name=server_name,
                    arguments=args
                )
            else:
                result = await mcp_registry.execute_command(
                    server_name=server_name
                )

            # Add result to context for the LLM
            context = []
            if result["type"] == "text":
                context.append({
                    "type": "mcp_result",
                    "server": server_name,
                    "content": result["content"]
                })

            # Create a message with MCP-specific metadata
            message_text = result["content"]
            message_metadata = {
                "mcp_result": {
                    "server": server_name,
                    "command": "",  # No specific command for direct server access
                    "arguments": args,
                    "type": result["type"],
                    "metadata": result.get("metadata", {})
                }
            }
            
            # Reply with the result and metadata
            self.reply(message_text, human_message, metadata=message_metadata)

            # Return context for LLM
            return {"context": context}
        except Exception as e:
            logger.error(f"Error processing MCP server command: {e}", exc_info=True)
            self.reply(f"Error executing MCP command: {str(e)}", human_message)
            return {"context": []}

    async def handle_exc(self, e: Exception, human_message: Message):
        """Handle exceptions from MCP server command execution"""
        logger.error(f"Error handling MCP server command: {e}")
        self.reply(f"Error executing MCP command: {str(e)}", human_message)