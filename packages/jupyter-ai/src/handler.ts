import { URLExt } from '@jupyterlab/coreutils';

import { ServerConnection } from '@jupyterlab/services';

// MCP feature detection
let _hasMcp: boolean | null = null;

const API_NAMESPACE = 'api/ai';

/**
 * Call the API extension
 *
 * @param endPoint API REST end point for the extension
 * @param init Initial values for the request
 * @returns The response body interpreted as JSON
 */
export async function requestAPI<T>(
  endPoint = '',
  init: RequestInit = {}
): Promise<T> {
  // Make request to Jupyter API
  const settings = ServerConnection.makeSettings();
  const requestUrl = URLExt.join(settings.baseUrl, API_NAMESPACE, endPoint);

  let response: Response;
  try {
    response = await ServerConnection.makeRequest(requestUrl, init, settings);
  } catch (error) {
    throw new ServerConnection.NetworkError(error as TypeError);
  }

  let data: any = await response.text();

  if (data.length > 0) {
    try {
      data = JSON.parse(data);
    } catch (error) {
      console.log('Not a JSON response body.', response);
    }
  }

  if (!response.ok) {
    throw new ServerConnection.ResponseError(response, data.message || data);
  }

  return data;
}

/**
 * Check if MCP is available
 * 
 * @returns A promise that resolves to a boolean indicating if MCP is available
 */
export async function checkMcpAvailability(): Promise<boolean> {
  if (_hasMcp !== null) {
    return _hasMcp;
  }
  
  try {
    // Try to access the MCP servers endpoint
    await requestAPI('mcp/servers');
    console.log('MCP is available - endpoint responded successfully');
    _hasMcp = true;
    return true;
  } catch (error) {
    // If we get a 404, MCP is not available
    if (error instanceof ServerConnection.ResponseError && error.response.status === 404) {
      console.warn('MCP is not available - endpoint returned 404');
      _hasMcp = false;
      return false;
    }
    
    // For server connection errors, MCP might be initializing
    if (error instanceof ServerConnection.NetworkError) {
      console.warn('MCP availability check had a network error - may be initializing', error);
      // Set to true and let the UI handle any issues
      _hasMcp = true;
      return true;
    }
    
    // For any other error, consider MCP available but with an issue
    console.warn('Error checking MCP availability', error);
    _hasMcp = true;
    return true;
  }
}

export namespace AiService {
  /**
   * The instantiation options for a data registry handler.
   */
  export interface IOptions {
    serverSettings?: ServerConnection.ISettings;
  }

  export type DescribeConfigResponse = {
    model_provider_id: string | null;
    embeddings_provider_id: string | null;
    api_keys: string[];
    send_with_shift_enter: boolean;
    fields: Record<string, Record<string, any>>;
    embeddings_fields: Record<string, Record<string, any>>;
    completions_fields: Record<string, Record<string, any>>;
    last_read: number;
    completions_model_provider_id: string | null;
  };

  export type UpdateConfigRequest = {
    model_provider_id?: string | null;
    embeddings_provider_id?: string | null;
    api_keys?: Record<string, string>;
    send_with_shift_enter?: boolean;
    fields?: Record<string, Record<string, any>>;
    last_read?: number;
    completions_model_provider_id?: string | null;
    completions_fields?: Record<string, Record<string, any>>;
    embeddings_fields?: Record<string, Record<string, any>>;
  };

  export async function getConfig(): Promise<DescribeConfigResponse> {
    return requestAPI<DescribeConfigResponse>('config');
  }

  export type EnvAuthStrategy = {
    type: 'env';
    name: string;
  };

  export type AwsAuthStrategy = {
    type: 'aws';
  };

  export type MultiEnvAuthStrategy = {
    type: 'multienv';
    names: string[];
  };

  export type AuthStrategy =
    | AwsAuthStrategy
    | EnvAuthStrategy
    | MultiEnvAuthStrategy
    | null;

  export type TextField = {
    type: 'text';
    key: string;
    label: string;
    format: string;
  };

  export type MultilineTextField = {
    type: 'text-multiline';
    key: string;
    label: string;
    format: string;
  };

  export type IntegerField = {
    type: 'integer';
    key: string;
    label: string;
  };

  export type Field = TextField | MultilineTextField | IntegerField;

  export type ListProvidersEntry = {
    id: string;
    name: string;
    model_id_label?: string;
    models: string[];
    help?: string;
    auth_strategy: AuthStrategy;
    registry: boolean;
    completion_models: string[];
    chat_models: string[];
    fields: Field[];
  };

  export type ListProvidersResponse = {
    providers: ListProvidersEntry[];
  };

  export async function listLmProviders(): Promise<ListProvidersResponse> {
    return requestAPI<ListProvidersResponse>('providers');
  }

  export async function listEmProviders(): Promise<ListProvidersResponse> {
    return requestAPI<ListProvidersResponse>('providers/embeddings');
  }

  export async function updateConfig(
    config: UpdateConfigRequest
  ): Promise<void> {
    return requestAPI<void>('config', {
      method: 'POST',
      body: JSON.stringify(config)
    });
  }

  export async function deleteApiKey(keyName: string): Promise<void> {
    return requestAPI<void>(`api_keys/${keyName}`, {
      method: 'DELETE'
    });
  }

  export type ListSlashCommandsEntry = {
    slash_id: string;
    description: string;
  };

  export type ListSlashCommandsResponse = {
    slash_commands: ListSlashCommandsEntry[];
  };

  export async function listSlashCommands(): Promise<ListSlashCommandsResponse> {
    return requestAPI<ListSlashCommandsResponse>('chats/slash_commands');
  }

  export type AutocompleteOption = {
    id: string;
    description: string;
    label: string;
    only_start: boolean;
  };

  export type ListAutocompleteOptionsResponse = {
    options: AutocompleteOption[];
  };

  export async function listAutocompleteOptions(): Promise<ListAutocompleteOptionsResponse> {
    return requestAPI<ListAutocompleteOptionsResponse>(
      'chats/autocomplete_options'
    );
  }

  export async function listAutocompleteArgOptions(
    partialCommand: string
  ): Promise<ListAutocompleteOptionsResponse> {
    return requestAPI<ListAutocompleteOptionsResponse>(
      'chats/autocomplete_options?partialCommand=' +
        encodeURIComponent(partialCommand)
    );
  }
}
