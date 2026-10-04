import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { strings } from "../strings";
import notFoundSource from "./NotFoundView.tsx?raw";

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;

beforeEach(() => {
  fetchMock = vi.fn<typeof fetch>(() => new Promise<Response>(() => {}));
  vi.stubGlobal("fetch", fetchMock);
});

describe("NotFoundView (C-5)", () => {
  it("NF-1 links back to / with no click handler or target", () => {
    render(<App pathname="/x" />);

    const link = screen.getByRole("link", { name: strings.notFound.homeLink });
    expect(link.getAttribute("href")).toBe("/");
    expect(link.hasAttribute("target")).toBe(false);
    expect(notFoundSource).not.toMatch(/onClick|target=/);
  });

  it("NF-2 never renders the requested path", () => {
    const { container } = render(<App pathname={`/does-not-exist-${crypto.randomUUID()}`} />);

    expect(container.textContent).not.toContain("does-not-exist");
  });

  it("NF-3 sets the Not Found document title", () => {
    render(<App pathname="/x" />);

    expect(document.title).toBe(strings.notFound.documentTitle);
  });

  it("NF-4 the link is the only focusable element", () => {
    const { container } = render(<App pathname="/x" />);

    const focusable = container.querySelectorAll("a[href],button,input,select,textarea,[tabindex]");
    expect(focusable).toHaveLength(1);
    expect(focusable[0]).toBe(screen.getByRole("link", { name: strings.notFound.homeLink }));
  });

  it("NF-6 makes no fetch call", () => {
    render(<App pathname="/x" />);

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
