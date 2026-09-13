import React, { useState, useEffect } from "react";
import { Home } from "./pages/Home";
import { Workspace } from "./pages/Workspace";

export type Route = "home" | "workspace";

export default function App() {
  const getInitialRoute = (): {
    route: Route;
    withExample: boolean;
    exampleId: string | null;
  } => {
    const hash = window.location.hash.toLowerCase();
    const pathname = window.location.pathname.toLowerCase();
    const search = window.location.search.toLowerCase();

    const withExample = search.includes("example=true") || hash.includes("example=true");
    const exampleMatch = hash.match(/example=([a-z0-9-]+)/);
    const exampleId =
      exampleMatch && exampleMatch[1] !== "true" ? exampleMatch[1] : null;

    if (hash.includes("workspace") || pathname.includes("workspace")) {
      return { route: "workspace", withExample, exampleId };
    }
    return { route: "home", withExample: false, exampleId: null };
  };

  const initial = getInitialRoute();
  const [route, setRoute] = useState<Route>(initial.route);
  const [withExample, setWithExample] = useState<boolean>(initial.withExample);
  const [exampleId, setExampleId] = useState<string | null>(initial.exampleId);

  useEffect(() => {
    const handleHashChange = () => {
      const current = getInitialRoute();
      setRoute(current.route);
      setWithExample(current.withExample);
      setExampleId(current.exampleId);
    };

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const navigateToWorkspace = (loadExample = true) => {
    setWithExample(loadExample);
    setExampleId(null);
    setRoute("workspace");
    window.location.hash = loadExample ? "#/workspace?example=true" : "#/workspace";
  };

  const navigateToExampleReport = (id: string) => {
    setWithExample(false);
    setExampleId(id);
    setRoute("workspace");
    window.location.hash = `#/workspace?example=${id}`;
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
        initialExampleId={exampleId}
      />
    );
  }

  return (
    <Home
      onNavigateWorkspace={navigateToWorkspace}
      onOpenExample={navigateToExampleReport}
    />
  );
}
