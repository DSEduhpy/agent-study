import type { CoreResponse } from "./coreClient";

export function parseCoreResponse(line: string): { requestId: number } & CoreResponse<unknown> | undefined {
  try {
    return JSON.parse(line) as { requestId: number } & CoreResponse<unknown>;
  } catch {
    return undefined;
  }
}