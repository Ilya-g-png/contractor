import { useEffect } from "react";
import { Shell } from "./Shell";
import { strings } from "./strings";

interface ErrorFallbackProps {
  reload?: () => void;
}

export function ErrorFallback({ reload = () => window.location.reload() }: ErrorFallbackProps) {
  useEffect(() => {
    document.title = strings.error.documentTitle;
  }, []);

  return (
    <Shell>
      <h1 className="page-heading">{strings.error.title}</h1>
      <p>
        <button type="button" className="button-primary" onClick={() => reload()}>
          {strings.error.reload}
        </button>
      </p>
    </Shell>
  );
}
