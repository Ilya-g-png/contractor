import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { strings } from "../strings";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>(() => new Promise<Response>(() => {})),
  );
});

describe("HomeView (C-3)", () => {
  it("HOME-1 the h1 precedes the status region", () => {
    render(<App pathname="/" />);

    const heading = screen.getByRole("heading", { level: 1, name: strings.home.title });
    const status = screen.getByRole("status");
    expect(heading.compareDocumentPosition(status) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("HOME-2 sets the document title to the product name", () => {
    render(<App pathname="/" />);

    expect(document.title).toBe(strings.productName);
  });

  it("HOME-3 contains no focusable elements", () => {
    const { container } = render(<App pathname="/" />);

    expect(
      container.querySelectorAll("a[href],button,input,select,textarea,[tabindex]"),
    ).toHaveLength(0);
  });

  it("HOME-5 the status region is present in the first committed render", () => {
    render(<App pathname="/" />);

    const status = screen.getByRole("status");
    expect(status.textContent).toBe(strings.apiStatus.checking);
  });
});
