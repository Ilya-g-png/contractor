import { resolveView } from "./router";
import { Shell } from "./Shell";
import { HomeView } from "./views/HomeView";
import { NotFoundView } from "./views/NotFoundView";

interface AppProps {
  pathname?: string;
}

export function App({ pathname = window.location.pathname }: AppProps) {
  return <Shell>{resolveView(pathname) === "home" ? <HomeView /> : <NotFoundView />}</Shell>;
}
