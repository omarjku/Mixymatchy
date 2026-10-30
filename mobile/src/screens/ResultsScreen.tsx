import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  Add01Icon,
  Download04Icon,
  LanguageSkillIcon,
  StopCircleIcon,
  VolumeHighIcon,
} from "@hugeicons/core-free-icons";
import { AppBar } from "@/components/AppBar";
import { ContradictionCard } from "@/components/ContradictionCard";
import { FactCard } from "@/components/FactCard";
import { PatientCard } from "@/components/PatientCard";
import { hasHistory } from "@/components/ValueHistory";
import { ViewTabs } from "@/components/ViewTabs";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Notice } from "@/components/ui/Notice";
import { Skeleton } from "@/components/ui/Skeleton";
import { roles } from "@/data/roles";
import { t } from "@/i18n/strings";
import { speak, stopSpeaking, useGermanVoiceAvailable } from "@/lib/speech";
import type { Fact, GuidelineCitation, PatientBrief, SourceCitation } from "@/types/fact";
import type { ResultsState } from "@/types/request";

// Results: patient header, contradictions first (never buried), then the required facts.
// Source/guideline open a simple sheet for now; the dialog-stack with the three tracks replaces it later.

type Sheet =
  | { kind: "source"; source: SourceCitation }
  | { kind: "guideline"; guideline: GuidelineCitation; factLabel: string }
  | { kind: "info"; title: string }
  | { kind: "sources"; title: string; sources: SourceCitation[] };

// Dashboard code (and recharts) loads only when the Dashboard tab is opened
const PatientDashboard = lazy(() => import("@/components/dashboard/PatientDashboard"));

type View = "overview" | "history" | "dashboard";

export function ResultsScreen() {
  const navigate = useNavigate();
  const state = useLocation().state as ResultsState | null;
  const voiceAvailable = useGermanVoiceAvailable();
  const [speaking, setSpeaking] = useState(false);
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [view, setView] = useState<View>("overview");

  const brief = state?.brief;
  const historyCount = brief?.facts.filter((f) => f.trust !== "not_documented" && hasHistory(f)).length ?? 0;
  const speechText = useMemo(() => (brief ? briefToSpeech(brief) : ""), [brief]);

  const speechEvents = useMemo(() => ({ onStart: () => setSpeaking(true), onEnd: () => setSpeaking(false) }), []);

  // Auto read-aloud when the clinician chose "Vorlesen" on the start screen
  useEffect(() => {
    if (!state?.readAloud || !voiceAvailable) return;
    speak(speechText, speechEvents);
    return () => stopSpeaking();
  }, [state?.readAloud, voiceAvailable, speechText, speechEvents]);

  // Stop any reading when leaving the screen
  useEffect(() => () => stopSpeaking(), []);

  // When the patient card scrolls under the AppBar, the bar shows the patient instead of the app name
  const [cardEl, setCardEl] = useState<HTMLElement | null>(null);
  const [cardVisible, setCardVisible] = useState(true);
  useEffect(() => {
    if (!cardEl) return;
    const observer = new IntersectionObserver(([entry]) => setCardVisible(entry.isIntersecting), {
      rootMargin: "-56px 0px 0px 0px", // the AppBar's height
    });
    observer.observe(cardEl);
    return () => observer.disconnect();
  }, [cardEl]);

  if (!state || !brief) return <Navigate to="/" replace />;

  const roleName = t(roles.find((r) => r.id === brief.role)?.nameKey ?? "role.gp.name");
  const generatedAt = new Intl.DateTimeFormat("de-DE", { dateStyle: "short", timeStyle: "short" }).format(
    new Date(brief.generatedAt),
  );

  function toggleReading() {
    if (speaking) stopSpeaking();
    else speak(speechText, speechEvents);
  }

  const showSource = (fact: Fact) => fact.source && setSheet({ kind: "source", source: fact.source });
  const showGuideline = (fact: Fact) =>
    fact.guideline && setSheet({ kind: "guideline", guideline: fact.guideline, factLabel: fact.label });
  const comingSoon = (title: string) => setSheet({ kind: "info", title });

  return (
    <>
      <AppBar
        back={{ label: t("action.back"), onClick: () => navigate("/") }}
        showTitle={!cardVisible}
        title={
          <p className="truncate leading-tight">
            <span className="block truncate text-[15px] font-semibold">{brief.patientLabel}</span>
            <span className="block truncate text-xs">
              {roleName} · {brief.task}
            </span>
          </p>
        }
        actions={
          <Button
            variant="icon"
            tone="onBrand"
            icon={speaking ? StopCircleIcon : VolumeHighIcon}
            label={
              voiceAvailable
                ? speaking
                  ? t("results.stopReading")
                  : t("results.readAloud")
                : t("results.noGermanVoice")
            }
            aria-pressed={speaking}
            disabled={!voiceAvailable}
            onClick={toggleReading}
            className={speaking ? "bg-white/20" : "disabled:opacity-40"}
          />
        }
        menuActions={[
          { id: "new", label: t("appbar.newRequest"), icon: Add01Icon, emphasis: true, onClick: () => navigate("/") },
          {
            id: "export",
            label: t("action.export"),
            icon: Download04Icon,
            onClick: () => comingSoon(t("action.export")),
          },
          {
            id: "language",
            label: `${t("results.language")}: Deutsch`,
            icon: LanguageSkillIcon,
            text: "DE",
            onClick: () => comingSoon(t("results.language")),
          },
        ]}
        contentClassName="md:max-w-3xl lg:max-w-6xl"
      />
      {/* Phone: one column. Tablet: facts in 2 columns. Desktop: patient + view controls in a sticky left column. */}
      <main className="mx-auto min-h-dvh max-w-md px-4 pb-10 pt-4 md:max-w-3xl md:px-8 lg:max-w-6xl">
        <div className="lg:grid lg:grid-cols-[360px_minmax(0,1fr)] lg:items-start lg:gap-8">
          <aside className="lg:sticky lg:top-20">
            <header ref={setCardEl}>
              <PatientCard brief={brief} roleName={roleName} generatedAt={generatedAt} />
            </header>

            <Notice tone="readonly" title={t("readonly.title")} className="mt-4">
              {t("readonly.body")}
            </Notice>

            <div className="mt-4">
              <ViewTabs
                tabs={[
                  { id: "overview", label: t("results.view.overview") },
                  { id: "history", label: t("results.view.history") },
                  { id: "dashboard", label: t("results.view.dashboard") },
                ]}
                active={view}
                onChange={setView}
                label={t("results.view.label")}
                panelId="facts-panel"
              />
              <p className="mt-2 px-2 text-xs text-ink-muted" aria-live="polite">
                {view === "overview"
                  ? t("results.view.overviewHint")
                  : view === "dashboard"
                    ? t("results.view.dashboardHint")
                    : historyCount > 0
                      ? t("results.view.historyAvailable", { n: historyCount, m: brief.facts.length })
                      : t("results.view.historyNone")}
              </p>
            </div>
          </aside>

          <div className="mt-6 space-y-6 lg:mt-2">
            {brief.contradictions.length > 0 && (
              <section aria-labelledby="contradictions-heading">
                <h2 id="contradictions-heading" className="mb-3 text-sm font-semibold text-contradiction-deep">
                  {t("results.contradictionsHeading")} ({brief.contradictions.length})
                </h2>
                <div className="space-y-3">
                  {brief.contradictions.map((c) => (
                    <ContradictionCard
                      key={c.id}
                      contradiction={c}
                      onPressSource={(source) => setSheet({ kind: "source", source })}
                    />
                  ))}
                </div>
              </section>
            )}

            {view === "dashboard" ? (
              <section id="facts-panel" aria-label={t("results.view.dashboard")}>
                <Suspense fallback={<Skeleton className="h-64 w-full rounded-2xl" />}>
                  <PatientDashboard
                    brief={brief}
                    onPressSources={(title, sources) => setSheet({ kind: "sources", title, sources })}
                  />
                </Suspense>
              </section>
            ) : (
              <section id="facts-panel" aria-labelledby="facts-heading">
                <h2 id="facts-heading" className="mb-3 text-sm font-semibold text-ink-muted">
                  {t("results.factsHeading")} ({brief.facts.length})
                </h2>
                {brief.facts.length === 0 ? (
                  <p className="rounded-2xl border border-dashed border-ink-faint/60 p-5 text-center text-sm text-ink-muted">
                    {t("results.empty")}
                  </p>
                ) : (
                  <div className="grid gap-3 md:grid-cols-2">
                    {brief.facts.map((fact) => (
                      <FactCard
                        key={fact.id}
                        fact={fact}
                        showHistory={view === "history"}
                        onPressSource={showSource}
                        onPressGuideline={showGuideline}
                        onPressFlag={() => comingSoon(t("results.flagTitle"))}
                      />
                    ))}
                  </div>
                )}
              </section>
            )}
          </div>
        </div>

        <p className="mt-8 text-center text-xs leading-snug text-ink-muted">{t("app.disclaimer")}</p>

        <Modal
          open={sheet !== null}
          onOpenChange={(open) => !open && setSheet(null)}
          title={sheetTitle(sheet)}
          description={sheetDescription(sheet)}
        >
          {sheet?.kind === "source" && <Excerpt text={sheet.source.excerpt} />}
          {sheet?.kind === "sources" && (
            <ul className="space-y-4">
              {uniqueSources(sheet.sources).map((s) => (
                <li key={s.documentId + s.excerpt}>
                  <p className="mb-1.5 text-xs font-medium text-ink-muted">{s.documentLabel}</p>
                  <Excerpt text={s.excerpt} />
                </li>
              ))}
            </ul>
          )}
          {sheet?.kind === "guideline" && (
            <>
              <Excerpt text={sheet.guideline.excerpt} />
              {sheet.guideline.reference && (
                <p className="mt-3 break-words text-xs text-ink-muted">{sheet.guideline.reference}</p>
              )}
            </>
          )}
          {sheet?.kind === "info" && (
            <>
              {sheet.title === t("results.flagTitle") && (
                <Notice tone="readonly" title={t("readonly.title")} className="mb-3">
                  {t("readonly.body")}
                </Notice>
              )}
              <p className="text-[15px] text-ink-muted">{t("results.comingSoon")}</p>
            </>
          )}
        </Modal>
      </main>
    </>
  );
}

function Excerpt({ text }: { text: string }) {
  return (
    <blockquote className="rounded-xl bg-primary-soft p-4 text-[15px] leading-relaxed text-ink">„{text}“</blockquote>
  );
}

function sheetTitle(sheet: Sheet | null): string {
  if (!sheet) return "";
  if (sheet.kind === "source") return sheet.source.documentLabel;
  if (sheet.kind === "guideline") return sheet.guideline.guidelineName;
  return sheet.title;
}

// The same passage can back both compared values (e.g. one letter states both); show it once
function uniqueSources(sources: SourceCitation[]): SourceCitation[] {
  const seen = new Set<string>();
  return sources.filter((s) => {
    const key = s.documentId + s.excerpt;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function sheetDescription(sheet: Sheet | null): string | undefined {
  if (sheet?.kind === "source" || sheet?.kind === "sources") return t("results.patientRecord");
  if (sheet?.kind === "guideline") return `${t("results.guidelineReason")}: ${sheet.factLabel}`;
  return undefined;
}

// Plain sentences for text to speech: patient, task, contradictions, then every fact with its trust tier.
function briefToSpeech(brief: PatientBrief): string {
  const parts = [sentence(brief.patientLabel), sentence(brief.task)];
  for (const c of brief.contradictions) parts.push(sentence(`${t("speech.contradiction")}: ${c.factLabel}`));
  for (const f of brief.facts) {
    if (f.trust === "not_documented") parts.push(sentence(`${f.label}: ${t("speech.notDocumented")}`));
    else parts.push(sentence(`${f.label}: ${f.value}`), sentence(t(`trust.${f.trust}`)));
  }
  return parts.join(" ");
}

// Ends text with a period unless it already ends in punctuation (avoids "58 J.." pauses)
function sentence(text: string): string {
  const trimmed = text.trim();
  return /[.!?…]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}
