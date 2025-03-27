/*
 * Copyright (c) Jupyter Development Team.
 * Distributed under the terms of the Modified BSD License.
 */

import { JupyterFrontEndPlugin } from '@jupyterlab/application';
import type { Contents } from '@jupyterlab/services';
import type { DocumentRegistry } from '@jupyterlab/docregistry';
import {
  IChatCommandProvider,
  IChatCommandRegistry,
  IInputModel,
  ChatCommand
} from '@jupyter/chat';
import { ServerConnection } from '@jupyterlab/services';
import { URLExt } from '@jupyterlab/coreutils';
import { terminalIcon } from '@jupyterlab/ui-components';

interface ListOptionsEntry {
  id: string;
  label: string;
  description: string;
  only_start: boolean;
}

interface ListOptionsResponse {
  options: ListOptionsEntry[];
}

const CONTEXT_COMMANDS_PROVIDER_ID =
  '@jupyter-ai/core:context-commands-provider';

/**
 * A command provider that provides completions for context commands like `@file` and `@mcp`.
 */
export class ContextCommandsProvider implements IChatCommandProvider {
  public id: string = CONTEXT_COMMANDS_PROVIDER_ID;
  private _context_commands: ChatCommand[] = [
    // TODO: add an icon!
    // import FindInPage from '@mui/icons-material/FindInPage';
    // may need to change the API to allow JSX els as icons
    {
      name: '@file',
      providerId: this.id,
      replaceWith: '@file:',
      description: 'Include a file with your prompt'
    },
    {
      name: '@mcp',
      providerId: this.id,
      replaceWith: '@mcp:',
      description: 'Include content from an MCP server resource with your prompt'
    }
  ];

  constructor(
    contentsManager: Contents.IManager,
    docRegistry: DocumentRegistry
  ) {
    this._contentsManager = contentsManager;
    this._docRegistry = docRegistry;
    this._serverSettings = ServerConnection.makeSettings();
  }

  async getChatCommands(inputModel: IInputModel) {
    // do nothing if the current word does not start with '@'.
    const currentWord = inputModel.currentWord;
    
    if (!currentWord || !currentWord.startsWith('@')) {
      return [];
    }


    if (currentWord.startsWith('@file:')) {
      const searchPath = currentWord.split('@file:')[1];
      const commands = await getPathCompletions(
        this._contentsManager,
        this._docRegistry,
        searchPath
      );
      return commands;
    }

    if (currentWord.startsWith('@mcp:')) {
      const commands = await getMcpCompletions(
        this._serverSettings,
        currentWord
      );
      return commands;
    }

    // otherwise, a context command has not yet been specified. return a list of
    // valid context commands.
    const commands = this._context_commands.filter(cmd =>
      cmd.name.startsWith(currentWord)
    );
    return commands;
  }

  async handleChatCommand(
    command: ChatCommand,
    inputModel: IInputModel
  ): Promise<void> {
    // no handling needed because `replaceWith` is set in each command.
    return;
  }

  private _contentsManager: Contents.IManager;
  private _docRegistry: DocumentRegistry;
  private _serverSettings: ServerConnection.ISettings;
}

/**
 * Returns the parent path and base name given a path. The parent path will
 * always include a trailing "/" if non-empty.
 *
 * Examples:
 *  - "package.json" => ["", "package.json"]
 *  - "foo/bar" => ["foo/", "bar"]
 *  - "a/b/c/d.txt" => ["a/b/c/", "d.txt"]
 *
 */
function getParentAndBase(path: string): [string, string] {
  const components = path.split('/');
  let parentPath: string;
  let basename: string;
  if (components.length === 1) {
    parentPath = '';
    basename = components[0];
  } else {
    parentPath = components.slice(0, -1).join('/') + '/';
    basename = components[components.length - 1] ?? '';
  }

  return [parentPath, basename];
}

/**
 * Fetches MCP completion options from the server based on the current input.
 * 
 * @param serverSettings The server connection settings
 * @param currentWord The current word being typed (starting with @mcp:)
 * @returns A list of ChatCommand objects to display as completion options
 */
async function getMcpCompletions(
  serverSettings: ServerConnection.ISettings,
  currentWord: string
): Promise<ChatCommand[]> {
  const commands: ChatCommand[] = [];
  const mcpArgs = currentWord.split('@mcp:')[1];

  try {
    const settings = ServerConnection.makeSettings();
    const requestUrl = URLExt.join(
      settings.baseUrl,
      'api/ai/chats/autocomplete_options'
    );
    
    const fullUrl = `${requestUrl}?partialCommand=${encodeURIComponent(currentWord)}`;
    
    const response = await ServerConnection.makeRequest(
      fullUrl,
      {},
      settings
    );
    
    if (!response.ok) {
      console.error(`Error fetching MCP completions: ${response.statusText}`);
      return [];
    }

    const data = await response.json() as ListOptionsResponse;
    
    for (const option of data.options) {
      const replaceText = option.label;
      
      const isServer = !mcpArgs.includes(':');
      const description = isServer 
        ? `${option.description}`
        : `${option.description}`;
        
      const command: ChatCommand = {
        name: option.id,
        providerId: CONTEXT_COMMANDS_PROVIDER_ID,
        description: description,
        ...(isServer && { icon: terminalIcon }),
        replaceWith: `@mcp:${replaceText}`
      };
      
      commands.push(command);
    }
  } catch (error) {
    console.error('Error fetching MCP completions:', error);
  }

  return commands;
}

async function getPathCompletions(
  contentsManager: Contents.IManager,
  docRegistry: DocumentRegistry,
  searchPath: string
) {
  const [parentPath, basename] = getParentAndBase(searchPath);
  const parentDir = await contentsManager.get(parentPath);
  const commands: ChatCommand[] = [];

  if (!Array.isArray(parentDir.content)) {
    // return nothing if parentDir is invalid / points to a non-directory file
    return [];
  }

  const children = parentDir.content
    // filter the children of the parent directory to only include file names that
    // start with the specified base name (case-insensitive).
    .filter((a: Contents.IModel) => {
      return a.name.toLowerCase().startsWith(basename.toLowerCase());
    })
    // sort the list, showing directories first while ensuring entries are shown
    // in alphabetic (lexicographically ascending) order.
    .sort((a: Contents.IModel, b: Contents.IModel) => {
      const aPrimaryKey = a.type === 'directory' ? -1 : 1;
      const bPrimaryKey = b.type === 'directory' ? -1 : 1;
      const primaryKey = aPrimaryKey - bPrimaryKey;
      const secondaryKey = a.name < b.name ? -1 : 1;

      return primaryKey || secondaryKey;
    });

  for (const child of children) {
    // get icon
    const { icon } = docRegistry.getFileTypeForModel(child);

    // compute list of results, while handling directories and non-directories
    // appropriately.
    const isDirectory = child.type === 'directory';
    let newCommand: ChatCommand;
    if (isDirectory) {
      newCommand = {
        name: child.name + '/',
        providerId: CONTEXT_COMMANDS_PROVIDER_ID,
        icon,
        description: 'Search this directory',
        replaceWith: '@file:' + parentPath + child.name + '/'
      };
    } else {
      newCommand = {
        name: child.name,
        providerId: CONTEXT_COMMANDS_PROVIDER_ID,
        icon,
        description: 'Attach this file',
        replaceWith: '@file:' + parentPath + child.name + ' '
      };
    }
    commands.push(newCommand);
  }

  return commands;
}

export const contextCommandsPlugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-ai/core:context-commands-plugin',
  description: 'Adds Jupyter AI context commands to the chat commands menu.',
  autoStart: true,
  requires: [IChatCommandRegistry],
  activate: (app, registry: IChatCommandRegistry) => {
    const { serviceManager, docRegistry } = app;
    registry.addProvider(
      new ContextCommandsProvider(serviceManager.contents, docRegistry)
    );
  }
};
