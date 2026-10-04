import { useEffect } from "react";
import { strings } from "../strings";

export function NotFoundView() {
  useEffect(() => {
    document.title = strings.notFound.documentTitle;
  }, []);

  return (
    <>
      <h1 className="page-heading">{strings.notFound.title}</h1>
      <p>
        <a className="text-link" href="/">
          {strings.notFound.homeLink}
        </a>
      </p>
    </>
  );
}
