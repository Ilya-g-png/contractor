export type ViewId = "home" | "not-found";

export function resolveView(pathname: string): ViewId {
  return pathname === "/" ? "home" : "not-found";
}
