import axe from "axe-core";

export const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

export async function axeViolations(context: Element): Promise<axe.Result[]> {
  const results = await axe.run(context, { runOnly: { type: "tag", values: WCAG_TAGS } });
  return results.violations;
}
