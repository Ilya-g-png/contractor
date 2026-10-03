import type { ReactNode } from "react";
import { strings } from "./strings";

interface ShellProps {
  children: ReactNode;
}

export function Shell({ children }: ShellProps) {
  return (
    <>
      <header className="shell-header">
        <div className="shell-container">
          <span className="shell-wordmark">{strings.productName}</span>
        </div>
      </header>
      <main className="shell-main">
        <div className="shell-container">{children}</div>
      </main>
    </>
  );
}
