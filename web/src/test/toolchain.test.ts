import browserslistToEsbuild from "browserslist-to-esbuild";
import { describe, expect, it } from "vitest";
import packageJson from "../../package.json";
import viteConfig from "../../vite.config";
import viteConfigSource from "../../vite.config.ts?raw";
import { axeViolations } from "./axe";

const ARCH_BROWSERSLIST = [
  "last 2 Chrome versions",
  "last 2 Edge versions",
  "last 2 Firefox versions",
  "last 2 Safari versions",
  "last 2 iOS versions",
];

describe("INV-W12 browser targets", () => {
  it("package.json browserslist equals the ARCH §6.21 list", () => {
    expect(packageJson.browserslist).toEqual(ARCH_BROWSERSLIST);
  });

  it("build.target and build.cssTarget come from browserslistToEsbuild()", () => {
    const expected = browserslistToEsbuild();
    expect(expected.length).toBeGreaterThan(0);
    expect(viteConfig.build?.target).toEqual(expected);
    expect(viteConfig.build?.cssTarget).toEqual(expected);
  });

  it("vite.config.ts contains no literal build target", () => {
    expect(viteConfigSource).toContain("browserslistToEsbuild()");
    expect(viteConfigSource).not.toMatch(/["'`](?:chrome|edge|firefox|safari|ios|opera|es)\d/i);
    expect(viteConfigSource).not.toMatch(/["'`](?:esnext|modules|baseline-widely-available)["'`]/);
  });
});

describe("axe harness", () => {
  it("reports WCAG violations in jsdom", async () => {
    const container = document.createElement("main");
    container.append(document.createElement("img"));
    document.body.append(container);

    const ids = (await axeViolations(container)).map((violation) => violation.id);

    expect(ids).toContain("image-alt");
    container.remove();
  });
});
