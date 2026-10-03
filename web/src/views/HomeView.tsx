import { useEffect } from "react";
import { ApiStatus } from "../components/ApiStatus";
import { strings } from "../strings";

export function HomeView() {
  useEffect(() => {
    document.title = strings.productName;
  }, []);

  return (
    <>
      <h1 className="page-heading">{strings.home.title}</h1>
      <ApiStatus />
    </>
  );
}
