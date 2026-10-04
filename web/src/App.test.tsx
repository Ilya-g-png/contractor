import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import packageJson from "../package.json";
import { App } from "./App";
import appSource from "./App.tsx?raw";
import { strings } from "./strings";

const productionSources = import.meta.glob<string>(["./**/*.{ts,tsx}", "!./**/*.test.{ts,tsx}"], {
  query: "?raw",
  import: "default",
  eager: true,
});

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>(() => new Promise<Response>(() => {})),
  );
});

describe("App (C-1)", () => {
  it("APP-1 renders Home at /", () => {
    render(<App pathname="/" />);

    expect(screen.getByRole("heading", { level: 1, name: strings.home.title })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: strings.notFound.title })).toBeNull();
  });

  it.each(["/x", "/index.html", "/a/b", "/x/", ""])(
    "APP-2 renders Not Found for %j with no status region",
    (pathname) => {
      render(<App pathname={pathname} />);

      expect(
        screen.getByRole("heading", { level: 1, name: strings.notFound.title }),
      ).toBeInTheDocument();
      expect(screen.queryByRole("status")).toBeNull();
    },
  );

  it.each(["/", "/x"])("APP-3 renders one banner, one main and one h1 at %j", (pathname) => {
    render(<App pathname={pathname} />);

    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("defaults pathname to window.location.pathname", () => {
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: strings.home.title })).toBeInTheDocument();
  });

  it("APP-4 web/src has no client-side history manipulation or hash routing", () => {
    const sources = Object.entries(productionSources);
    expect(sources.length).toBeGreaterThan(0);
    for (const [path, source] of sources) {
      expect(source, path).not.toMatch(/history\.(pushState|replaceState)/);
      expect(source, path).not.toMatch(/addEventListener\(\s*["']popstate/);
      expect(source, path).not.toContain("location.hash");
    }
  });

  it("APP-5 App imports only local modules and dependencies are react and react-dom", () => {
    const specifiers = [...appSource.matchAll(/from\s+["']([^"']+)["']/g)].map((match) => match[1]);
    expect(specifiers.length).toBeGreaterThan(0);
    for (const specifier of specifiers) {
      expect(specifier).toMatch(/^\.\.?\//);
    }
    expect(Object.keys(packageJson.dependencies).sort()).toEqual(["react", "react-dom"]);
  });
});
