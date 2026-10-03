import { describe, expect, it } from "vitest";
import { resolveView } from "./router";

describe("resolveView (IC-5.2, INV-W9)", () => {
  it('resolves "/" to home', () => {
    expect(resolveView("/")).toBe("home");
  });

  it.each(["/x", "/index.html", "/a/b", "/x/", ""])("resolves %j to not-found", (pathname) => {
    expect(resolveView(pathname)).toBe("not-found");
  });

  it("never consults a hash fragment", () => {
    expect(resolveView("/#/")).toBe("not-found");
    expect(resolveView("#/")).toBe("not-found");
  });
});
