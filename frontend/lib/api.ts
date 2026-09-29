export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SERVER_API_URL = process.env.API_URL_INTERNAL ?? API_URL;

export type Health = {
  status: string;
  version: string;
  environment: string;
};

export async function fetchHealth(): Promise<Health | null> {
  try {
    const response = await fetch(`${SERVER_API_URL}/healthz`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as Health;
  } catch {
    return null;
  }
}
