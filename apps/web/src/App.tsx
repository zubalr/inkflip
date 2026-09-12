import React, { useState, useEffect } from "react";
import { Home } from "./pages/Home";
import { Workspace } from "./pages/Workspace";
import type { ViewerDoc } from "./features/viewer/types";

export type Route = "home" | "workspace";

export default function App() {
  const getInitialRoute = (): { route: Route; withExample: boolean } => {
    const hash = window.location.hash.toLowerCase();
    const pathname = window.location.pathname.toLowerCase();
    const search = window.location.search.toLowerCase();

    const withExample = search.includes("example=true") || hash.includes("example=true");

    if (hash.includes("workspace") || pathname.includes("workspace")) {
      return { route: "workspace", withExample };
    }
    return { route: "home", withExample: false };
  };

  const initial = getInitialRoute();
  const [route, setRoute] = useState<Route>(initial.route);
  const [withExample, setWithExample] = useState<boolean>(initial.withExample);
  const [activeDoc, setActiveDoc] = useState<ViewerDoc | null>(null);

  useEffect(() => {
    const handleHashChange = () => {
      const current = getInitialRoute();
      setRoute(current.route);
      setWithExample(current.withExample);
    };

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const navigateToWorkspace = (loadExample = true) => {
    setWithExample(loadExample);
    setRoute("workspace");
    window.location.hash = loadExample ? "#/workspace?example=true" : "#/workspace";
  };

  const navigateToHome = () => {
    setRoute("home");
    window.location.hash = "#/";
  };

  if (route === "workspace") {
    return (
      <Workspace
        onNavigateHome={navigateToHome}
        initialWithExample={withExample}
        initialDoc={activeDoc}
        onImportReport={(doc) => setActiveDoc(doc)}
        onOpenFile={(_file) => {
          setActiveDoc(null);
        }}
        onCloseDoc={() => {
          setActiveDoc(null);
        }}
      />
    );
  }

  return <Home onNavigateWorkspace={navigateToWorkspace} />;
}
