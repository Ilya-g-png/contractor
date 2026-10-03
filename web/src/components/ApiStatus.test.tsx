import { readFileSync } from "node:fs";
import { render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";
import { strings } from "../strings";
import { ApiStatus } from "./ApiStatus";
import apiStatusSource from "./ApiStatus.tsx?raw";

const appCss = readFileSync(`${import.meta.dirname}/../styles/app.css`, "utf8");

type FetchImpl = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const STATUS_TEXTS: readonly string[] = Object.values(strings.apiStatus);

function stubFetch(impl: FetchImpl) {
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

function pending(): Promise<Response> {
  return new Promise<Response>(() => {});
}

function pendingUntilAborted(_input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
  });
}

async function expectSettled(text: string, state: string) {
  const status = screen.getByRole("status");
  await waitFor(() => expect(status.textContent).toBe(text));
  expect(status.getAttribute("data-state")).toBe(state);
}

describe("ApiStatus (C-4)", () => {
  it("STS-1 starts in checking before fetch settles", () => {
    stubFetch(pending);

    render(<ApiStatus />);

    const status = screen.getByRole("status");
    expect(status.textContent).toBe(strings.apiStatus.checking);
    expect(status.getAttribute("data-state")).toBe("checking");
  });

  it("STS-2 200 ok becomes available", async () => {
    stubFetch(async () => json({ status: "ok" }));

    render(<ApiStatus />);

    await expectSettled(strings.apiStatus.available, "available");
  });

  it.each<[string, FetchImpl]>([
    ['200 {"status":"degraded"}', async () => json({ status: "degraded" })],
    ["200 non-JSON", async () => new Response("not json", { status: 200 })],
    ["503", async () => json({ status: "ok" }, 503)],
    ["rejected fetch", () => Promise.reject(new TypeError("Failed to fetch"))],
  ])("STS-2 %s becomes unavailable", async (_label, impl) => {
    stubFetch(impl);

    render(<ApiStatus />);

    await expectSettled(strings.apiStatus.unavailable, "unavailable");
  });

  it("STS-2 the 5 s timeout becomes unavailable", async () => {
    const timeout = new AbortController();
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeout.signal);
    stubFetch(pendingUntilAborted);

    render(<ApiStatus />);
    expect(screen.getByRole("status").textContent).toBe(strings.apiStatus.checking);
    timeout.abort(new DOMException("The operation timed out.", "TimeoutError"));

    await expectSettled(strings.apiStatus.unavailable, "unavailable");
  });

  it("STS-3 calls fetch once with /api/v1/health by default", async () => {
    const fetchMock = stubFetch(async () => json({ status: "ok" }));

    render(<ApiStatus />);
    await expectSettled(strings.apiStatus.available, "available");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/health");
  });

  it("STS-3 uses a given baseUrl with trailing slashes trimmed", async () => {
    const fetchMock = stubFetch(async () => json({ status: "ok" }));

    render(<ApiStatus baseUrl="/custom//" />);
    await expectSettled(strings.apiStatus.available, "available");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/custom/health");
  });

  it("STS-4 unmount aborts the request without React warnings", async () => {
    const consoleError = vi.spyOn(console, "error");
    const fetchMock = stubFetch(pendingUntilAborted);

    const { unmount } = render(<ApiStatus />);
    const signal = fetchMock.mock.calls[0]?.[1]?.signal;
    unmount();
    await Promise.resolve();

    expect(signal?.aborted).toBe(true);
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("STS-5 a late ok after a terminal state changes nothing", async () => {
    let resolveFirst: (response: Response) => void = () => {};
    const fetchMock = stubFetch(() =>
      fetchMock.mock.calls.length === 1
        ? new Promise<Response>((resolve) => {
            resolveFirst = resolve;
          })
        : Promise.resolve(json({ status: "ok" }, 503)),
    );

    render(
      <StrictMode>
        <ApiStatus />
      </StrictMode>,
    );
    await expectSettled(strings.apiStatus.unavailable, "unavailable");
    expect(fetchMock).toHaveBeenCalledTimes(2);

    resolveFirst(json({ status: "ok" }));
    await new Promise((resolve) => setTimeout(resolve, 0));

    const status = screen.getByRole("status");
    expect(status.textContent).toBe(strings.apiStatus.unavailable);
    expect(status.getAttribute("data-state")).toBe("unavailable");
  });

  it("STS-6 rerender with a new baseUrl after a terminal state changes nothing", async () => {
    const fetchMock = stubFetch(async () => json({ status: "ok" }, 503));

    const { rerender } = render(<ApiStatus />);
    await expectSettled(strings.apiStatus.unavailable, "unavailable");
    fetchMock.mockImplementation(async () => json({ status: "ok" }));
    rerender(<ApiStatus baseUrl="/other" />);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(screen.getByRole("status").textContent).toBe(strings.apiStatus.unavailable);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("STS-7 an HTML-bearing body never reaches the DOM", async () => {
    stubFetch(async () => json({ status: "<img src=x onerror=alert(1)>", version: "<b>x</b>" }));

    const { container } = render(<ApiStatus />);
    await expectSettled(strings.apiStatus.unavailable, "unavailable");

    expect(container.innerHTML).not.toContain("onerror");
    expect(container.innerHTML).not.toContain("<b>x</b>");
    expect(container.querySelector("img, b")).toBeNull();
  });

  it.each<[string, FetchImpl]>([
    ["checking", pending],
    ["available", async () => json({ status: "ok" })],
    ["unavailable", async () => json({}, 500)],
  ])("STS-8 text is a status string and STS-9 the dot is empty in %s", async (state, impl) => {
    stubFetch(impl);

    render(<ApiStatus />);
    const status = screen.getByRole("status");
    await waitFor(() => expect(status.getAttribute("data-state")).toBe(state));

    expect(STATUS_TEXTS).toContain(status.textContent);
    const dot = status.querySelector('[aria-hidden="true"]');
    expect(dot).not.toBeNull();
    expect(dot?.textContent).toBe("");
  });

  it("STS-10 source has no raw HTML, timers or retry loop", () => {
    expect(apiStatusSource).not.toMatch(
      /dangerouslySetInnerHTML|innerHTML|setInterval|setTimeout|while\s*\(|for\s*\(/,
    );
  });

  it("STS-11 CSS maps each data-state to its status token with no motion", () => {
    expect(appCss).toMatch(
      /\.api-status\[data-state="checking"\][^{]*\{[^}]*var\(--color-status-neutral\)/,
    );
    expect(appCss).toMatch(
      /\.api-status\[data-state="available"\][^{]*\{[^}]*var\(--color-status-ok\)/,
    );
    expect(appCss).toMatch(
      /\.api-status\[data-state="unavailable"\][^{]*\{[^}]*var\(--color-status-error\)/,
    );
    expect(appCss).not.toMatch(/\b(transition|animation)\s*:/);
  });
});
