export interface Prompt {
  id: string;
  name: string;
  description?: string;
  content: string;
}

export function usePrompts() {
  // TODO: Replace with real prompt query
  return {
    prompts: [] as Prompt[],
    isLoading: false,
    error: null,
    refetch: () => {},
  };
}
