import json
from typing import List, Optional

from jupyter_ai.mcp import MCPServerRegistry
from jupyter_ai.models import ListOptionsEntry
from jupyterlab_chat.models import Message

from .base import (
    BaseCommandContextProvider,
    ContextCommand,
    ContextProviderException,
)

MCP_CONTEXT_TEMPLATE = """
MCP context from server '{server}': {resource_name}
```
{content}
```
""".strip()


class McpContextProvider(BaseCommandContextProvider):
    id = "mcp"
    help = "Include content from an MCP server"
    requires_arg = True
    header = "Following are contents of referenced MCP context:"

    async def get_arg_options(self, arg_prefix: str) -> List[ListOptionsEntry]:
        """Get autocomplete options for MCP servers

        Format is @server_name:resource_name or @server_name:prompt_name
        
        Args:
            arg_prefix: The current partial command, starting after @mcp:
            
        Returns:
            A list of autocomplete options
        """
        options = []
        
        if ":" not in arg_prefix:
            try:
                # servers currently need to be load at startup time
                registered_servers = list(MCPServerRegistry.registry.keys())
                
                for server_name in registered_servers:
                    if server_name.lower().startswith(arg_prefix.lower()):
                        options.append(
                            self._make_arg_option(
                                arg=server_name + ":",
                                description=f"{MCPServerRegistry.registry[server_name]["description"]}",
                                is_complete=False
                            )
                        )
            except Exception as e:
                self.log.error(f"Error getting MCP servers: {e}")
        
        else:
            server_name, _, prefix = arg_prefix.partition(":")
            
            try:
                async with MCPServerRegistry.start_server(server_name) as client:
                    res = await client.initialize()
                    capabilities = res.capabilities
                    
                    if capabilities.resources:
                        try:
                            resources_response = await client.list_resources()
                            resources = resources_response.resources
                        except Exception as e:
                            self.log.error(f"Error calling list_resources: {e}")
                            raise
                    
                        for resource in resources:
                            if resource.name.lower().startswith(prefix.lower()):
                                options.append(
                                    self._make_arg_option(
                                        arg=f"{server_name}:{resource.uri}",
                                        description=f"{resource.description}",
                                        is_complete=True,
                                        display_name=resource.name.lower()
                                    )
                                )
                    
                    elif capabilities.prompts:
                        try:
                            prompts_response = await client.list_prompts()
                            prompts = prompts_response.prompts
                        except Exception as e:
                            self.log.error(f"Error calling list_prompts: {e}")
                            raise
                    
                        for prompt in prompts:
                            if prompt.name.lower().startswith(prefix.lower()):
                                arg_template = ""
                                # major hack: get arguments and send to user to complete
                                if hasattr(prompt, "arguments") and prompt.arguments:
                                    arg_parts = []
                                    for arg in prompt.arguments:
                                        if hasattr(arg, "required") and arg.required:
                                            arg_name = arg.name
                                            arg_parts.append(f'"{arg_name}": ""')
                                    if arg_parts:
                                        arg_template = "{" + ", ".join(arg_parts) + "}"
                                
                                completion_arg = f"{server_name}:{prompt.name}"
                                if arg_template:
                                    completion_arg += arg_template
                                    desc = f"{prompt.description} (requires arguments)"
                                else:
                                    desc = f"{prompt.description}"
                                
                                options.append(
                                    self._make_arg_option(
                                        arg=completion_arg,
                                        description=desc,
                                        is_complete=True,
                                        display_name=prompt.name.lower()
                                    )
                                )
            except Exception as e:
                self.log.error(f"Error getting MCP resources: {e}")
    
        return options

    async def _make_context_prompt(
        self, message: Message, commands: List[ContextCommand]
    ) -> str:
        """Create a context prompt from MCP resources"""

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

        if ":" not in arg:
            raise ContextProviderException(
                f"Invalid MCP resource reference: `{command}`. "
                f"Format must be @mcp:server_name:resource_name."
            )

        server_name, _, remaining = arg.partition(":")
        
        arguments = {}
        if "{" in remaining:
            name, _, arg_str = remaining.partition("{")
            if arg_str.endswith("}"):
                arg_str = arg_str[:-1]
                
            try:
                arg_str = "{" + arg_str + "}"
                arguments = json.loads(arg_str)
            except json.JSONDecodeError as e:
                self.log.error(f"Error parsing arguments: {e}")
                raise ContextProviderException(
                    f"Invalid argument format in MCP reference: `{command}`. "
                    f"Arguments must be valid JSON. Error: {str(e)}"
                )
        else:
            name = remaining

        async with MCPServerRegistry.start_server(server_name) as client:
            res = await client.initialize()
            capabilities = res.capabilities
            
            if capabilities.resources:
                resource = await client.read_resource(name)
                return MCP_CONTEXT_TEMPLATE.format(
                    server=server_name,
                    resource_name=name,
                    content=resource.contents[0].text,
                )
            elif capabilities.prompts:
                if arguments:
                    result = await client.get_prompt(name, arguments=arguments)
                    return MCP_CONTEXT_TEMPLATE.format(
                        server=server_name,
                        resource_name=name,
                        content=result.messages[0].content.text,
                    )

                else:
                    prompt = await client.get_prompt(name)
                    return MCP_CONTEXT_TEMPLATE.format(
                        server=server_name,
                        resource_name=name,
                        content=prompt.messages[0].content.text,
                    )
            else:
                raise ContextProviderException(
                    f"MCP resource not found: `{command}`. "
                    f"Resource '{name}' not found in server '{server_name}'."
                )

    def _replace_command(self, command: ContextCommand) -> str:
        """Replace @mcp:server:resource with server:resource in the prompt"""
        arg = command.arg or ""
        return f"'{arg}'"
        
    def _make_arg_option(
        self,
        arg: str,
        *,
        is_complete: bool = True,
        description: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> ListOptionsEntry:
        arg = arg.replace("\\ ", " ").replace(" ", "\\ ")
        
        if display_name:
            name_to_display = display_name
        else:
            name_to_display = arg.split(":")[0] if ":" in arg else arg
        
        label = arg + (" " if is_complete else "")
        return ListOptionsEntry(
            id=name_to_display,
            description=description or self.help,
            label=label,
            only_start=self.only_start,
        )