import { readFileSync } from "node:fs";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { ErrorFallback } from "./ErrorFallback";
import { axeViolations } from "./test/axe";

const ownedSources = import.meta.glob<string>(
  [
    "./{main,App,Shell,ErrorBoundary,ErrorFallback}.tsx",
    "./views/*.tsx",
    "./components/*.tsx",
    "!./**/*.test.tsx",
  ],
  { query: "?raw", import: "default", eager: true },
);

const appCss = readFileSync(`${import.meta.dirname}/styles/app.css`, "utf8");

type FetchImpl = () => Promise<Response>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("INV-W4 / SC-009 axe (WCAG 2.2 AA)", () => {
  it.each<[string, FetchImpl]>([
    ["checking", () => new Promise<Response>(() => {})],
    ["available", async () => json({ status: "ok" })],
    ["unavailable", async () => json({}, 503)],
  ])("HOME-4 Home has zero violations while %s", async (state, impl) => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(impl));

    const { container } = render(<App pathname="/" />);
    await waitFor(() => expect(screen.getByRole("status").getAttribute("data-state")).toBe(state));

    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("status").getAttribute("aria-live")).toBe("polite");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("NF-5 Not Found has zero violations", async () => {
    const { container } = render(<App pathname="/x" />);

    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("EF-7 Error fallback has zero violations", async () => {
    const { container } = render(<ErrorFallback reload={vi.fn()} />);

    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("static conventions over owned files (X-1a, X-2, X-3, X-5)", () => {
  const sources = Object.entries(ownedSources);

  it("covers every owned component file", () => {
    expect(sources).toHaveLength(8);
  });

  it("X-1a has no JSX text literals", () => {
    for (const [path, source] of sources) {
      expect(source, path).not.toMatch(/>\s*[A-Za-z][^<{]*</);
    }
  });

  it("X-2, X-3, X-5 have no raw HTML, inline styles or programmatic focus", () => {
    for (const [path, source] of sources) {
      expect(source, path).not.toMatch(
        /dangerouslySetInnerHTML|\.innerHTML|insertAdjacentHTML|document\.write|style=\{|tabIndex|tabindex|autoFocus|\.focus\(/,
      );
    }
  });

  it("app.css has no motion, no removed outlines and a focus ring", () => {
    expect(appCss).not.toMatch(/\b(transition|animation)[\w-]*\s*:/);
    expect(appCss).not.toMatch(/outline\s*:\s*(none|0)\b/);
    expect(appCss).toMatch(/:focus-visible[^{]*\{[^}]*outline:\s*2px solid var\(--color-focus\)/);
  });

  it("app.css is mobile-first with only the 640px and 1024px breakpoints", () => {
    const queries = [...appCss.matchAll(/@media\s*([^{]+)\{/g)].map((match) => match[1]?.trim());
    expect(queries.length).toBeGreaterThan(0);
    for (const query of queries) {
      expect(["(min-width: 640px)", "(min-width: 1024px)"]).toContain(query);
    }
    expect(appCss).not.toMatch(/display\s*:\s*none/);
  });

  it("app.css uses logical properties only", () => {
    expect(appCss).not.toMatch(
      /(^|[\s;{])(?:(?:margin|padding|border)-(?:left|right|top|bottom)|left|right|top|bottom|(?:min-|max-)?(?:width|height))\s*:/m,
    );
    expect(appCss).not.toMatch(/position\s*:\s*(sticky|fixed)/);
  });
});
