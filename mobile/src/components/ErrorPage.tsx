import { Home01Icon, RefreshIcon } from "@hugeicons/core-free-icons";
import { AppBar } from "@/components/AppBar";
import { Button } from "@/components/ui/Button";
import { t } from "@/i18n/strings";

// Full-page error, built from Watermelon UI's error-1 (registry.watermelon.sh/r/error-1.json): large
// dashed-outline code over a faint periwinkle grid that fades out toward the edges. Buttons are our own
// (error-1's pill faded on hover). Used for 404 and for the crash screen.

export interface ErrorPageProps {
  code: string;
  title: string;
  description: string;
  onReload?: () => void; // crash screen: offer a reload next to "home"
}

export function ErrorPage({ code, title, description, onReload }: ErrorPageProps) {
  return (
    <>
      <AppBar contentClassName="md:max-w-2xl" />
      <main className="relative flex min-h-[calc(100dvh-3.5rem)] items-center justify-center overflow-hidden px-6 py-16">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.12] [mask-image:radial-gradient(circle_at_center,black_10%,transparent_65%)]"
          style={{
            backgroundImage:
              "linear-gradient(var(--color-primary-strong) 1px, transparent 1px), linear-gradient(90deg, var(--color-primary-strong) 1px, transparent 1px)",
            backgroundSize: "24px 24px",
          }}
        />

        <section
          aria-labelledby="error-title"
          className="relative z-10 mx-auto flex w-full max-w-md flex-col items-center text-center"
        >
          <svg viewBox="0 0 800 300" className="w-full max-w-[18rem] select-none sm:max-w-sm" aria-hidden>
            <text
              x="50%"
              y="50%"
              textAnchor="middle"
              dominantBaseline="central"
              fill="var(--color-primary)"
              fillOpacity={0.18}
              stroke="var(--color-primary-strong)"
              strokeWidth={3}
              strokeDasharray="36 18"
              fontWeight={800}
              fontSize={code.length <= 3 ? 300 : 190}
              letterSpacing={-8}
            >
              {code}
            </text>
          </svg>

          <h1 id="error-title" className="mt-2 text-xl font-semibold leading-snug tracking-tight sm:text-2xl">
            {title}
          </h1>
          <p className="mt-2 max-w-sm text-[15px] leading-relaxed text-ink-muted">{description}</p>

          <div className="mt-8 flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
            {onReload && (
              <Button variant="primary" icon={RefreshIcon} onClick={onReload}>
                {t("error.reload")}
              </Button>
            )}
            <Button
              variant={onReload ? "secondary" : "primary"}
              icon={Home01Icon}
              className={onReload ? "h-12" : undefined}
              onClick={() => window.location.assign("/")}
            >
              {t("error.home")}
            </Button>
          </div>
        </section>
      </main>
    </>
  );
}

export function NotFoundScreen() {
  return <ErrorPage code="404" title={t("error.404.title")} description={t("error.404.body")} />;
}
