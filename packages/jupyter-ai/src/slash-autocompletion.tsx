import {
  AutocompleteCommand,
  IAutocompletionCommandsProps
} from '@jupyter/chat';
import Download from '@mui/icons-material/Download';
import FindInPage from '@mui/icons-material/FindInPage';
import Help from '@mui/icons-material/Help';
import MoreHoriz from '@mui/icons-material/MoreHoriz';
import MenuBook from '@mui/icons-material/MenuBook';
import School from '@mui/icons-material/School';
import HideSource from '@mui/icons-material/HideSource';
import AutoFixNormal from '@mui/icons-material/AutoFixNormal';
import Terminal from '@mui/icons-material/Terminal';
import { Box, Typography } from '@mui/material';
import React from 'react';
import { AiService, checkMcpAvailability } from './handler';
import { mcpService } from './services/mcp-service';

type SlashCommandOption = AutocompleteCommand & {
  id: string;
  description: string;
};

/**
 * List of icons per slash command, shown in the autocomplete popup.
 *
 * This list of icons should eventually be made configurable. However, it is
 * unclear whether custom icons should be defined within a Lumino plugin (in the
 * frontend) or served from a static server route (in the backend).
 */
const DEFAULT_SLASH_COMMAND_ICONS: Record<string, JSX.Element> = {
  ask: <FindInPage />,
  clear: <HideSource />,
  export: <Download />,
  fix: <AutoFixNormal />,
  generate: <MenuBook />,
  help: <Help />,
  learn: <School />,
  mcp: <Terminal />,
  unknown: <MoreHoriz />
};

/**
 * Renders an option shown in the slash command autocomplete.
 */
function renderSlashCommandOption(
  optionProps: React.HTMLAttributes<HTMLLIElement>,
  option: SlashCommandOption
): JSX.Element {
  const icon =
    option.id in DEFAULT_SLASH_COMMAND_ICONS
      ? DEFAULT_SLASH_COMMAND_ICONS[option.id]
      : DEFAULT_SLASH_COMMAND_ICONS.unknown;

  return (
    <li {...optionProps}>
      <Box sx={{ lineHeight: 0, marginRight: 4, opacity: 0.618 }}>{icon}</Box>
      <Box sx={{ flexGrow: 1 }}>
        <Typography
          component="span"
          sx={{
            fontSize: 'var(--jp-ui-font-size1)'
          }}
        >
          {option.label}
        </Typography>
        <Typography
          component="span"
          sx={{ opacity: 0.618, fontSize: 'var(--jp-ui-font-size0)' }}
        >
          {' — ' + option.description}
        </Typography>
      </Box>
    </li>
  );
}

/**
 * The autocompletion command properties to add to the registry.
 */
export const autocompletion: IAutocompletionCommandsProps = {
  opener: '/',
  commands: async () => {
    // Get standard slash commands
    const slashCommands = (await AiService.listSlashCommands()).slash_commands;
    const standardCommands = slashCommands.map<SlashCommandOption>(slashCommand => ({
      id: slashCommand.slash_id,
      label: '/' + slashCommand.slash_id + ' ',
      description: slashCommand.description
    }));
    
    // Add MCP server commands if available
    try {
      // First check if MCP is available
      const checkMcpAvailable = await checkMcpAvailability();
      
      if (checkMcpAvailable) {
        console.log('MCP available, fetching commands for autocompletion...');
        const mcpCommands = await mcpService.getCommands();
        console.log('MCP commands fetched successfully:', mcpCommands);
        
        const mcpSlashCommands = mcpCommands.map<SlashCommandOption>(mcpCommand => ({
          id: mcpCommand.serverName,
          label: '/' + mcpCommand.serverName + ' ',
          description: mcpCommand.description || `MCP Server: ${mcpCommand.serverName}`
        }));
        
        return [...standardCommands, ...mcpSlashCommands];
      } else {
        console.log('MCP not available, skipping MCP commands in autocompletion');
        return standardCommands;
      }
    } catch (error) {
      // Log the error but don't block autocompletion
      console.error('Error fetching MCP commands for autocompletion:', error);
      return standardCommands;
    }
  },
  props: {
    renderOption: renderSlashCommandOption,
    // Add custom handler for argument suggestions
    getOptionLabel: (option: any) => option.label || '',
    onChange: async (_event: any, _value: any, _reason: any) => {
      try {
        // Custom argument handling will be implemented in the component
        return;
      } catch (error) {
        console.error('Error handling MCP command arguments:', error);
      }
    }
  }
};
