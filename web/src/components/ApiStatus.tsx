import { useEffect, useState } from "react";
import { fetchHealth, type HealthResult } from "../api/health";
import { API_BASE_URL } from "../config";
import { strings } from "../strings";

export type ApiStatusState = "checking" | HealthResult;

interface ApiStatusProps {
  baseUrl?: string;
}

export function ApiStatus({ baseUrl = API_BASE_URL }: ApiStatusProps) {
  const [mountBaseUrl] = useState(baseUrl);
  const [state, setState] = useState<ApiStatusState>("checking");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    void fetchHealth(mountBaseUrl, controller.signal).then((result) => {
      if (active) {
        setState((current) => (current === "checking" ? result : current));
      }
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [mountBaseUrl]);

  return (
    <p
      className="api-status"
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-state={state}
    >
      <span className="api-status__dot" aria-hidden="true"></span>
      <span className="api-status__text">{strings.apiStatus[state]}</span>
    </p>
  );
}
