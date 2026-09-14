import React, { useState, useEffect, useRef } from "react";
import { Home } from "./pages/Home";
import { Workspace } from "./pages/Workspace";
import { HelpPage } from "./pages/help";
import {
  resolvePublicExampleId,
  SYNTHETIC_EXAMPLE_FIXTURE_ID,
} from "./features/gallery/loader";

export type Route = "home" | "workspace" | "help";

function parseWorkspaceExample(hash: string, search: string): {
  withExample: boolean;
  exampleId: string | null;
  loadSyntheticFixture: boolean;
} {
  const withExample = search.includes("example=true") || hash.includes("example=true");
  const exampleMatch = hash.match(/example=([a-z0-9-]+)/);
  const raw = exampleMatch?.[1] ?? null;
  const loadSyntheticFixture =
    raw === SYNTHETIC_EXAMPLE_FIXTURE_ID && __INKFLIP_TEST_HOOKS__;
  if (loadSyntheticFixture) {
    return { withExample: false, exampleId: null, loadSyntheticFixture: true };
  }
  return {
    withExample,
    exampleId: resolvePublicExampleId(withExample, raw),
    loadSyntheticFixture: false,
  };
}

export default function App() {
  const getInitialRoute = (): {
    route: Route;
    withExample: boolean;
    exampleId: string | null;
    loadSyntheticFixture: boolean;
  } => {
    const hash = window.location.hash.toLowerCase();
    const pathname = window.location.pathname.toLowerCase();
    const search = window.location.search.toLowerCase();
    const example = parseWorkspaceExample(hash, search);

    if (hash.includes("help") || pathname.includes("help")) {
      return { route: "help", withExample: false, exampleId: null, loadSyntheticFixture: false };
    }
    if (hash.includes("workspace") || pathname.includes("workspace")) {
      return { route: "workspace", ...example };
    }
    return { route: "home", withExample: false, exampleId: null, loadSyntheticFixture: false };
  };

  const initial = getInitialRoute();
  const [route, setRoute] = useState<Route>(initial.route);
  const [withExample, setWithExample] = useState<boolean>(initial.withExample);
  const [exampleId, setExampleId] = useState<string | null>(initial.exampleId);
  const [loadSyntheticFixture, setLoadSyntheticFixture] = useState<boolean>(
    initial.loadSyntheticFixture,
  );
  const [workspaceEpoch, setWorkspaceEpoch] = useState<number>(0);

  // Preserve workspace state across temporary Help visits
  const [workspaceEverMounted, setWorkspaceEverMounted] = useState<boolean>(
    initial.route === "workspace"
  );
  const lastWorkspaceHash = useRef<string>(
    initial.route === "workspace" ? window.location.hash || "#/workspace" : "#/workspace"
  );
  const lastFocusBeforeHelp = useRef<HTMLElement | null>(null);

  const previousRoute = useRef<Route>(route);

  useEffect(() => {
    const handleHashChange = () => {
      const current = getInitialRoute();
      if (current.route === "workspace") {
        setWorkspaceEverMounted(true);
        lastWorkspaceHash.current = window.location.hash || "#/workspace";
        setWithExample(current.withExample);
        setExampleId(current.exampleId);
        setLoadSyntheticFixture(current.loadSyntheticFixture);
      } else if (current.route === "home") {
        setWorkspaceEverMounted(false);
        setWithExample(false);
        setExampleId(null);
        setLoadSyntheticFixture(false);
      }
      setRoute(current.route);
    };

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  // Restore focus to triggering element when returning from Help to Workspace
  useEffect(() => {
    if (previousRoute.current === "help" && route === "workspace") {
      const timer = setTimeout(() => {
        if (
          lastFocusBeforeHelp.current &&
          typeof lastFocusBeforeHelp.current.focus === "function" &&
          document.contains(lastFocusBeforeHelp.current)
        ) {
          lastFocusBeforeHelp.current.focus();
        } else {
          const helpBtn = document.getElementById("btn-header-help");
          if (helpBtn) {
            helpBtn.focus();
          }
        }
      }, 50);
      return () => clearTimeout(timer);
    }
    previousRoute.current = route;
  }, [route]);

  const navigateToWorkspace = (loadExample = false) => {
    setWorkspaceEverMounted(true);
    setWithExample(loadExample);
    setExampleId(resolvePublicExampleId(loadExample, null));
    setLoadSyntheticFixture(false);
    if (loadExample) {
      setWorkspaceEpoch((e) => e + 1);
    }
    setRoute("workspace");
    const targetHash = loadExample ? "#/workspace?example=true" : "#/workspace";
    lastWorkspaceHash.current = targetHash;
    window.location.hash = targetHash;
  };

  const navigateToExampleReport = (id: string) => {
    setWorkspaceEverMounted(true);
    setWithExample(false);
    setExampleId(id);
    setLoadSyntheticFixture(false);
    setWorkspaceEpoch((e) => e + 1);
    setRoute("workspace");
    const targetHash = `#/workspace?example=${id}`;
    lastWorkspaceHash.current = targetHash;
    window.location.hash = targetHash;
  };

  const navigateToHome = () => {
    setWorkspaceEverMounted(false);
    setRoute("home");
    window.location.hash = "#/";
  };

  const navigateToHelp = () => {
    lastFocusBeforeHelp.current = document.activeElement as HTMLElement | null;
    if (route === "workspace") {
      lastWorkspaceHash.current = window.location.hash || "#/workspace";
    }
    setRoute("help");
    window.location.hash = "#/help";
  };

  const returnToWorkspace = () => {
    setRoute("workspace");
    const targetHash = lastWorkspaceHash.current || "#/workspace";
    window.location.hash = targetHash;
  };

  if (route === "home") {
    return (
      <Home
        onNavigateWorkspace={(withExample?: boolean) => navigateToWorkspace(Boolean(withExample))}
        onOpenExample={navigateToExampleReport}
        onNavigateHelp={navigateToHelp}
      />
    );
  }

  return (
    <>
      {route === "help" && (
        <HelpPage
          onNavigateHome={navigateToHome}
          onNavigateWorkspace={() => navigateToWorkspace(false)}
          onReturnToWorkspace={returnToWorkspace}
          onOpenExample={() => navigateToWorkspace(true)}
          hasActiveWorkspace={workspaceEverMounted}
        />
      )}

      {workspaceEverMounted && (
        <div
          id="workspace-container"
          style={{ display: route === "workspace" ? undefined : "none" }}
          hidden={route !== "workspace"}
          inert={route !== "workspace" ? true : undefined}
        >
          <Workspace
            key={`${loadSyntheticFixture ? "fixture" : withExample}-${exampleId ?? "default"}-${workspaceEpoch}`}
            onNavigateHome={navigateToHome}
            onNavigateHelp={navigateToHelp}
            onLoadPublicExample={() => navigateToWorkspace(true)}
            initialExampleId={exampleId}
            loadSyntheticFixture={loadSyntheticFixture}
          />
        </div>
      )}
    </>
  );
}
