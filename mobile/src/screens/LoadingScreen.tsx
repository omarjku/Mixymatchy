import { useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Alert02Icon } from "@hugeicons/core-free-icons";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Skeleton } from "@/components/ui/Skeleton";
import { roles } from "@/data/roles";
import { t } from "@/i18n/strings";
import { BriefTimeoutError, fetchPatientBriefWithTimeout } from "@/lib/api";
import { setResults } from "@/lib/session";
import type { BriefRequest, ResultsState } from "@/types/request";

// Fetches the brief, showing a skeleton in the shape of the results screen, then replaces itself with
// /results (so Back from results returns to the start screen, not here).

type LoadError = "timeout" | "generic";

export function LoadingScreen() {
  const navigate = useNavigate();
  const request = useLocation().state as BriefRequest | null;
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<LoadError | null>(null);

  useEffect(() => {
    if (!request) return;
    const controller = new AbortController();
    fetchPatientBriefWithTimeout(request.role, request.task, controller.signal)
      .then((brief) => {
        const state: ResultsState = { brief, readAloud: request.readAloud };
        setResults(state); // memory only: patient data never goes into history.state
        navigate("/results", { replace: true });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // screen left or re-run; not a failure
        setError(err instanceof BriefTimeoutError ? "timeout" : "generic");
      });
    return () => controller.abort();
  }, [request, attempt, navigate]);

  if (!request) return <Navigate to="/" replace />;

  const roleName = t(roles.find((r) => r.id === request.role)!.nameKey);

  if (error) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-md flex-col px-4 pt-[env(safe-area-inset-top)]">
        <div className="my-auto py-10" role="alert">
          <Icon icon={Alert02Icon} size={28} className="text-contradiction" />
          <h1 className="mt-4 text-xl font-semibold leading-snug">{t("loading.error.title")}</h1>
          <p className="mt-2 text-[15px] text-ink-muted">
            {error === "timeout" ? t("loading.error.timeout") : t("loading.error.generic")}
          </p>
          <p className="mt-4 text-sm text-ink-muted">
            {roleName} · {request.task}
          </p>
          <div className="mt-8 flex flex-col gap-2">
            <Button
              variant="primary"
              fullWidth
              onClick={() => {
                setError(null);
                setAttempt((n) => n + 1);
              }}
            >
              {t("action.retry")}
            </Button>
            <Button variant="secondary" fullWidth onClick={() => navigate("/", { replace: true })}>
              {t("action.back")}
            </Button>
          </div>
        </div>
      </main>
    );
  }

  return (
    // Same responsive layout as ResultsScreen so nothing jumps when the data arrives
    <main
      className="mx-auto flex min-h-dvh max-w-md flex-col px-4 pb-8 pt-[env(safe-area-inset-top)] md:max-w-3xl md:px-8 lg:max-w-6xl"
      aria-busy="true"
    >
      {/* Top bar: back, then export + language on the right */}
      <div className="flex h-14 items-center justify-between">
        <Skeleton className="size-10 rounded-full" />
        <div className="flex gap-2">
          <Skeleton className="size-10 rounded-full" />
          <Skeleton className="size-10 rounded-full" />
        </div>
      </div>

      <p role="status" className="mb-4 text-sm text-ink-muted">
        <span className="font-medium text-ink">{t("loading.title")}</span>
        <br />
        {roleName} · {request.task}
      </p>

      <div className="lg:grid lg:grid-cols-[360px_minmax(0,1fr)] lg:items-start lg:gap-8">
        <div>
          {/* Patient card */}
          <div className="rounded-lg border border-line bg-surface p-4">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="mt-3 h-6 w-48" />
            <div className="mt-4 flex gap-2">
              <Skeleton className="h-8 w-20 rounded-full" />
              <Skeleton className="h-8 w-20 rounded-full" />
              <Skeleton className="h-8 w-20 rounded-full" />
            </div>
          </div>
          {/* View tabs */}
          <Skeleton className="mt-4 h-12 w-full rounded-full" />
        </div>

        <div className="mt-4 lg:mt-0">
          {/* Contradiction */}
          <Skeleton className="h-20 w-full rounded-lg" />

          {/* Fact cards */}
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="rounded-lg border border-line bg-surface p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <Skeleton className="h-3 w-24" />
                    <Skeleton className="mt-3 h-5 w-40" />
                  </div>
                  <Skeleton className="h-6 w-24 rounded-full" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
