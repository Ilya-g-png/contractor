export type HealthResult = "available" | "unavailable";

const TIMEOUT_MS = 5000;

export async function fetchHealth(baseUrl: string, signal: AbortSignal): Promise<HealthResult> {
  try {
    const response = await fetch(`${baseUrl.replace(/\/+$/, "")}/health`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: AbortSignal.any([signal, AbortSignal.timeout(TIMEOUT_MS)]),
    });
    if (!response.ok) {
      return "unavailable";
    }
    const body: unknown = await response.json();
    return typeof body === "object" && body !== null && "status" in body && body.status === "ok"
      ? "available"
      : "unavailable";
  } catch {
    return "unavailable";
  }
}
