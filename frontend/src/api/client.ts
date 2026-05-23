import type { ConfigResponse, DashboardResponse, SeriesResponse } from "../types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function getConfig() {
  return request<ConfigResponse>("/api/config");
}

export function getDashboard(date?: string) {
  const suffix = date ? `?date=${encodeURIComponent(date)}` : "";
  return request<DashboardResponse>(`/api/dashboard${suffix}`);
}

export function getSeries(sector: string, date?: string) {
  const params = new URLSearchParams({ sector });
  if (date) params.set("date", date);
  return request<SeriesResponse>(`/api/series?${params.toString()}`);
}

export function simulate(overrides: Record<string, unknown>, sector: string, date?: string) {
  return request<{ dashboard: DashboardResponse; series: SeriesResponse; config: Record<string, unknown> }>(
    "/api/simulate",
    {
      method: "POST",
      body: JSON.stringify({ overrides, sector, date })
    }
  );
}
