import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";
import errorBoundarySource from "./ErrorBoundary.tsx?raw";
import mainSource from "./main.tsx?raw";
import { strings } from "./strings";

const productionSources = import.meta.glob<string>(["./**/*.{ts,tsx}", "!./**/*.test.{ts,tsx}"], {
  query: "?raw",
  import: "default",
  eager: true,
});

function Thrower({ message }: { message: string }): never {
  throw new Error(message);
}

function renderThrowing() {
  vi.spyOn(console, "error").mockImplementation(() => {});
  return render(
    <ErrorBoundary>
      <Thrower message={`boom-${crypto.randomUUID()}`} />
    </ErrorBoundary>,
  );
}

describe("ErrorBoundary (C-6)", () => {
  it("EB-1 a throwing child renders the fallback inside a non-empty main", () => {
    renderThrowing();

    expect(
      screen.getByRole("heading", { level: 1, name: strings.error.title }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: strings.error.reload })).toBeInTheDocument();
    expect(screen.getByRole("main")).not.toBeEmptyDOMElement();
  });

  it("EB-2 the fallback shows no error message or stack", () => {
    const { container } = renderThrowing();

    expect(container.textContent).not.toContain("boom-");
    expect(container.textContent).not.toContain("Error");
    expect(container.textContent).not.toContain("at ");
  });

  it("EB-3 renders children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>ok</p>
      </ErrorBoundary>,
    );

    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: strings.error.title })).toBeNull();
  });

  it("EB-4 main.tsx mounts exactly one ErrorBoundary around App and none exists elsewhere", () => {
    expect(mainSource.match(/<ErrorBoundary>/g)).toHaveLength(1);
    expect(mainSource).toMatch(/<ErrorBoundary>\s*<App \/>\s*<\/ErrorBoundary>/);
    for (const [path, source] of Object.entries(productionSources)) {
      if (!path.endsWith("/main.tsx")) {
        expect(source, path).not.toMatch(/<ErrorBoundary[\s>]/);
      }
      if (!path.endsWith("/ErrorBoundary.tsx")) {
        expect(source, path).not.toContain("getDerivedStateFromError");
        expect(source, path).not.toContain("componentDidCatch");
      }
    }
  });

  it("EB-5 sends no telemetry, logs nothing and touches no storage", () => {
    expect(errorBoundarySource).not.toMatch(
      /fetch|sendBeacon|console\.|localStorage|sessionStorage|indexedDB|cookie/,
    );
  });
});
