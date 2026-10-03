import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchHealth } from "./health";

function stubFetch(impl: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) {
  const fetchMock = vi.fn<typeof fetch>(impl);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function pendingUntilAborted(_input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
  });
}

function signalOf(fetchMock: ReturnType<typeof stubFetch>): AbortSignal {
  const signal = fetchMock.mock.calls[0]?.[1]?.signal;
  if (!signal) {
    throw new Error("fetch was called without a signal");
  }
  return signal;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("fetchHealth (IC-5.1)", () => {
  it('resolves "available" for 200 {"status":"ok"}', async () => {
    stubFetch(async () => json({ status: "ok", version: "0.1.0" }));

    await expect(fetchHealth("/api/v1", new AbortController().signal)).resolves.toBe("available");
  });

  it.each<[string, () => Promise<Response>]>([
    ['200 {"status":"degraded"}', async () => json({ status: "degraded" })],
    ["200 non-JSON", async () => new Response("not json", { status: 200 })],
    ["200 JSON null", async () => json(null)],
    ['200 JSON "ok" string', async () => json("ok")],
    ["503", async () => json({ status: "ok" }, 503)],
    ["rejected fetch", () => Promise.reject(new TypeError("Failed to fetch"))],
    [
      "synchronously throwing fetch",
      () => {
        throw new TypeError("boom");
      },
    ],
  ])('resolves "unavailable" for %s', async (_label, impl) => {
    stubFetch(impl);

    await expect(fetchHealth("/api/v1", new AbortController().signal)).resolves.toBe("unavailable");
  });

  it('resolves "unavailable" when the 5000 ms timeout fires', async () => {
    const timeout = new AbortController();
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeout.signal);
    const fetchMock = stubFetch(pendingUntilAborted);

    const result = fetchHealth("/api/v1", new AbortController().signal);
    timeout.abort(new DOMException("The operation timed out.", "TimeoutError"));

    await expect(result).resolves.toBe("unavailable");
    expect(timeoutSpy).toHaveBeenCalledExactlyOnceWith(5000);
    expect(signalOf(fetchMock).aborted).toBe(true);
  });

  it('resolves "unavailable" when the caller aborts', async () => {
    const caller = new AbortController();
    const fetchMock = stubFetch(pendingUntilAborted);

    const result = fetchHealth("/api/v1", caller.signal);
    caller.abort();

    await expect(result).resolves.toBe("unavailable");
    expect(signalOf(fetchMock).aborted).toBe(true);
  });

  it("requests GET /api/v1/health with only Accept: application/json", async () => {
    const fetchMock = stubFetch(async () => json({ status: "ok" }));

    await fetchHealth("/api/v1", new AbortController().signal);

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/health");
    expect(init?.method).toBe("GET");
    expect(init?.headers).toEqual({ Accept: "application/json" });
    expect(init?.body).toBeUndefined();
    expect(init?.credentials).toBeUndefined();
  });

  it.each([
    ["/x//", "/x/health"],
    ["/api/v1/", "/api/v1/health"],
    ["https://api.example.test/api/v1", "https://api.example.test/api/v1/health"],
  ])("trims trailing slashes: %j -> %j", async (baseUrl, expected) => {
    const fetchMock = stubFetch(async () => json({ status: "ok" }));

    await fetchHealth(baseUrl, new AbortController().signal);

    expect(fetchMock.mock.calls[0]?.[0]).toBe(expected);
  });

  it("combines the caller signal with a 5000 ms timeout signal", async () => {
    const timeout = new AbortController();
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeout.signal);
    const anySpy = vi.spyOn(AbortSignal, "any");
    const caller = new AbortController();
    const fetchMock = stubFetch(async () => json({ status: "ok" }));

    await fetchHealth("/api/v1", caller.signal);

    expect(timeoutSpy).toHaveBeenCalledExactlyOnceWith(5000);
    expect(anySpy).toHaveBeenCalledExactlyOnceWith([caller.signal, timeout.signal]);
    const signal = signalOf(fetchMock);
    expect(signal).not.toBe(caller.signal);
    expect(signal).not.toBe(timeout.signal);
    expect(signal.aborted).toBe(false);
    timeout.abort(new DOMException("The operation timed out.", "TimeoutError"));
    expect(signal.aborted).toBe(true);
  });
});

describe("API_BASE_URL (DC-8)", () => {
  it("defaults to same-origin /api/v1", async () => {
    vi.stubEnv("VITE_DOGWATCH_API_BASE_URL", undefined);

    const { API_BASE_URL } = await import("../config");

    expect(API_BASE_URL).toBe("/api/v1");
  });

  it("takes the build-time VITE_DOGWATCH_API_BASE_URL override", async () => {
    vi.stubEnv("VITE_DOGWATCH_API_BASE_URL", "https://api.example.test/api/v1");

    const { API_BASE_URL } = await import("../config");

    expect(API_BASE_URL).toBe("https://api.example.test/api/v1");
  });
});
