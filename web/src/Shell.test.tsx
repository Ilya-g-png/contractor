import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Shell } from "./Shell";
import shellSource from "./Shell.tsx?raw";
import { strings } from "./strings";

describe("Shell (C-2)", () => {
  it("SHL-1 renders one banner with the product name and one main", () => {
    render(
      <Shell>
        <h1>t</h1>
      </Shell>,
    );

    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("banner").textContent).toBe(strings.productName);
  });

  it("SHL-2 banner holds no heading, link, button or tab stop", () => {
    render(
      <Shell>
        <h1>t</h1>
      </Shell>,
    );

    expect(
      screen.getByRole("banner").querySelectorAll("h1,h2,h3,h4,h5,h6,a,button,[tabindex]"),
    ).toHaveLength(0);
  });

  it("SHL-3 renders children inside main and no other landmark", () => {
    render(
      <Shell>
        <h1>t</h1>
      </Shell>,
    );

    const heading = screen.getByRole("heading", { level: 1 });
    expect(within(screen.getByRole("main")).getByRole("heading", { level: 1 })).toBe(heading);
    expect(screen.getByRole("banner").contains(heading)).toBe(false);
  });

  it("SHL-4 uses no hooks", () => {
    expect(shellSource).not.toMatch(/\buse[A-Z]\w*\s*\(/);
    expect(shellSource).not.toContain("useEffect");
  });
});
