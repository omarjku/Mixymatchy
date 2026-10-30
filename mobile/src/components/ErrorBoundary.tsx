import { Component, type ErrorInfo, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { ErrorPage } from "@/components/ErrorPage";
import { t } from "@/i18n/strings";

// Catches render errors anywhere below it and shows the crash screen instead of a blank page.
// Keyed by the route path, so navigating elsewhere (e.g. the logo/home link) clears the error.

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Second Eye screen crashed", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <ErrorPage
        code={t("error.crash.code")}
        title={t("error.crash.title")}
        description={t("error.crash.body")}
        onReload={() => window.location.reload()}
      />
    );
  }
}

export function ErrorBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return <Boundary key={pathname}>{children}</Boundary>;
}
