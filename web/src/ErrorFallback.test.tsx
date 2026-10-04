import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorFallback } from "./ErrorFallback";
import errorFallbackSource from "./ErrorFallback.tsx?raw";
import { strings } from "./strings";

describe("ErrorFallback (C-7)", () => {
  it("EF-1 each activation of the native button calls reload exactly once", () => {
    const reload = vi.fn();
    render(<ErrorFallback reload={reload} />);

    const button = screen.getByRole("button", { name: strings.error.reload });
    expect(button).toBeInstanceOf(HTMLButtonElement);

    fireEvent.click(button);
    expect(reload).toHaveBeenCalledOnce();
    fireEvent.click(button);
    expect(reload).toHaveBeenCalledTimes(2);
    expect(reload.mock.calls.every((args) => args.length === 0)).toBe(true);
  });

  it("EF-2 the button has type=button and is the only focusable element", () => {
    const { container } = render(<ErrorFallback reload={vi.fn()} />);

    const button = screen.getByRole("button", { name: strings.error.reload });
    expect(button.getAttribute("type")).toBe("button");
    const focusable = container.querySelectorAll("a[href],button,input,select,textarea,[tabindex]");
    expect(focusable).toHaveLength(1);
    expect(focusable[0]).toBe(button);
  });

  it("EF-3 renders one banner with the product name, one main and one h1", () => {
    render(<ErrorFallback reload={vi.fn()} />);

    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getByRole("banner").textContent).toBe(strings.productName);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(strings.error.title);
  });

  it("EF-4 sets the error document title", () => {
    render(<ErrorFallback reload={vi.fn()} />);

    expect(document.title).toBe(strings.error.documentTitle);
  });

  it("EF-5 does not move focus to the button", () => {
    render(<ErrorFallback reload={vi.fn()} />);

    expect(document.activeElement).not.toBe(
      screen.getByRole("button", { name: strings.error.reload }),
    );
    expect(errorFallbackSource).not.toContain(".focus(");
  });

  it("EF-6 uses no lazy code, data fetching or error prop", () => {
    expect(errorFallbackSource).not.toMatch(/import\(|lazy\(|fetch/);
    expect(errorFallbackSource).not.toMatch(/\berror\??\s*:/);
  });
});
