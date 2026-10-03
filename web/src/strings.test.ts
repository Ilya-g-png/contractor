import { describe, expect, it } from "vitest";
import { strings } from "./strings";

describe("strings (DC-10, CC X-1)", () => {
  it("holds exactly the CC X-1 catalogue", () => {
    expect(strings).toEqual({
      productName: "Dogwatch",
      home: { title: "Dashboard" },
      notFound: {
        title: "Page not found",
        homeLink: "Back to home",
        documentTitle: "Page not found · Dogwatch",
      },
      apiStatus: {
        checking: "Checking API…",
        available: "API available",
        unavailable: "API unavailable",
      },
      error: {
        title: "Something went wrong",
        reload: "Reload page",
        documentTitle: "Something went wrong · Dogwatch",
      },
    });
  });

  it("uses the FS-fixed copy verbatim", () => {
    expect(strings.productName).toBe("Dogwatch");
    expect(strings.apiStatus.checking).toBe("Checking API…");
    expect(strings.apiStatus.available).toBe("API available");
    expect(strings.apiStatus.unavailable).toBe("API unavailable");
    expect(strings.notFound.title).toBe("Page not found");
    expect(strings.error.title).toBe("Something went wrong");
    expect(strings.error.reload).toBe("Reload page");
  });

  it("uses a single U+2026 ellipsis, not three dots", () => {
    expect(strings.apiStatus.checking.endsWith("…")).toBe(true);
    expect(strings.apiStatus.checking).not.toContain("...");
  });
});
