import { lazy, type ReactNode, Suspense, useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Add01Icon, LanguageSkillIcon, StopCircleIcon, VolumeHighIcon } from "@hugeicons/core-free-icons";
import { AppBar } from "@/components/AppBar";
import { ContradictionCard } from "@/components/ContradictionCard";
import { FactRows, RowSource, TrendLine } from "@/components/FactCard";
import { FactList } from "@/components/FactList";
import { HistoryLog } from "@/components/HistoryLog";
import { PatientCard } from "@/components/PatientCard";
import { SourceViewer } from "@/components/SourceViewer";
import { ViewTabs } from "@/components/ViewTabs";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/ui/Skeleton";
import { mockBriefInEnglish } from "@/data/mockFacts";
import { roles } from "@/data/roles";
import { toggleLocale, useLocale } from "@/i18n/locale";
import { t } from "@/i18n/strings";
import { USE_MOCK } from "@/lib/api";
import { getResults } from "@/lib/session";
import { formatDate } from "@/lib/stats";
import { speak, stopSpeaking, useVoiceAvailable } from "@/lib/speech";
import { cn } from "@/lib/utils";
import type { Fact, FactRow, GuidelineCitation, KeyFactLine, PatientBrief, SourceCitation } from "@/types/fact";
import type { BriefRequest } from "@/types/request";
import { KeepDoses } from "@/components/ui/KeepDoses";

// Results: patient + how the request was read, banners (not authorised / not applicable / task not
// recognised), then three levels with different content:
//   Overview: plain text, what matters now: contradictions, the facts the task needs (P1), "Also relevant" (P2)
//   Details:  the in-depth view: charts of changes, medication changes, calculations, record checks, open items
//   History:  a plain log of every dated entry, newest first
// Every source link opens the original letter.

type View = "overview" | "details" | "history";

// Details level: charts (recharts) load only when the tab is opened
const DetailsView = lazy(() => import("@/components/details/DetailsView"));
type Viewer = { citations: SourceCitation[]; index: number; title: string };

export function ResultsScreen() {
  const navigate = useNavigate();
  // In memory only (src/lib/session.ts): patient data never goes into history.state.
  const state = getResults();
  const voiceAvailable = useVoiceAvailable();
  const locale = useLocale();
  const [speaking, setSpeaking] = useState(false);
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [guideline, setGuideline] = useState<{ guideline: GuidelineCitation; label: string } | null>(null);
  const [view, setView] = useState<View>("overview");
  // Answer-first (docs/DECISIONS.md 20): key facts first, everything else behind one "Show more"
  const [expanded, setExpanded] = useState(false);

  // Mock mode in English: the invented German demo data shown in English (letter quotes stay German)
  const brief = useMemo(
    () => (state?.brief && USE_MOCK && locale === "en" ? mockBriefInEnglish(state.brief, formatDate) : state?.brief),
    [state?.brief, locale],
  );
  const speechText = useMemo(() => (brief ? briefToSpeech(brief) : ""), [brief]);
  const speechEvents = useMemo(() => ({ onStart: () => setSpeaking(true), onEnd: () => setSpeaking(false) }), []);

  useEffect(() => {
    if (!state?.readAloud || !voiceAvailable) return;
    speak(speechText, speechEvents);
    return () => stopSpeaking();
  }, [state?.readAloud, voiceAvailable, speechText, speechEvents]);
  useEffect(() => () => stopSpeaking(), []);

  // When the patient card scrolls under the AppBar, the bar shows the patient instead of the app name
  const [cardEl, setCardEl] = useState<HTMLElement | null>(null);
  const [cardVisible, setCardVisible] = useState(true);
  useEffect(() => {
    if (!cardEl) return;
    const observer = new IntersectionObserver(([entry]) => setCardVisible(entry.isIntersecting), {
      rootMargin: "-56px 0px 0px 0px",
    });
    observer.observe(cardEl);
    return () => observer.disconnect();
  }, [cardEl]);

  if (!state || !brief) return <Navigate to="/" replace />;

  // The backend's own label for the role it read; the chip name only in mock mode. Never a "GP" default.
  const roleName =
    brief.roleLabel ?? (roles.find((r) => r.id === brief.role && r.id !== "other") ? t(roles.find((r) => r.id === brief.role)!.nameKey) : brief.role);
  const generatedAt = formatDate(brief.generatedAt) // same numeric format as every date in the brief;
  const mode = brief.screenMode ?? "task";
  const notAuthorised = mode === "not_authorised";
  // No task, no data (docs/DECISIONS.md 19): a greeting or a bare role gets a banner, nothing from the record.
  const needsTask = mode === "needs_task";
  const gated = notAuthorised || needsTask;
  const stats = brief.stats ?? {};

  const openSources = (citations: SourceCitation[], index: number, title: string) =>
    citations.length > 0 && setViewer({ citations, index, title });
  const showSource = (fact: Fact) => openSources(fact.sources ?? (fact.source ? [fact.source] : []), 0, fact.label);
  const showGuideline = (fact: Fact) => fact.guideline && setGuideline({ guideline: fact.guideline, label: fact.label });

  // Re-run with a suggested sentence (task not recognised, not authorised): typed as free text.
  const rerun = (situation: string) => {
    const request: BriefRequest = { role: "other", task: situation, readAloud: false };
    navigate("/loading", { state: request });
  };

  function toggleReading() {
    if (speaking) stopSpeaking();
    else speak(speechText, speechEvents);
  }

  const contradictions = brief.contradictions.filter((c) => (c.tier ?? "contradiction") === "contradiction");
  const droppedOnScreen = (brief.gaps ?? []).filter((g) => g.kind === "dropped").length;
  const blindSpot = stats.blind_spot ?? 0;
  const taskConcepts = stats.task_concepts ?? 0;
  const otherIssues = stats.other_record_issues ?? 0;
  const keyFacts = brief.keyFacts ?? [];
  const answerFirst = !gated && keyFacts.length > 0;
  const overview = !gated && view === "overview";
  const showDetails = overview && (!answerFirst || expanded);

  return (
    <>
      <AppBar
        back={{ label: t("action.back"), onClick: () => navigate("/") }}
        showTitle={!cardVisible}
        title={
          <p className="truncate leading-tight">
            <span className="block truncate text-[15px] font-semibold">{brief.patientLabel}</span>
            <span className="block truncate text-xs">
              {roleName}: {brief.taskLabel ?? brief.task}
            </span>
          </p>
        }
        actions={
          <Button
            variant="icon"
            tone="onBrand"
            icon={speaking ? StopCircleIcon : VolumeHighIcon}
            label={voiceAvailable ? (speaking ? t("results.stopReading") : t("results.readAloud")) : t("results.noGermanVoice")}
            aria-pressed={speaking}
            disabled={!voiceAvailable}
            onClick={toggleReading}
            className={speaking ? "bg-white/20" : "disabled:opacity-40"}
          />
        }
        menuActions={[
          { id: "new", label: t("appbar.newRequest"), icon: Add01Icon, emphasis: true, onClick: () => navigate("/") },
          {
            id: "language",
            label: t("appbar.language"),
            icon: LanguageSkillIcon,
            text: locale === "en" ? "EN" : "DE",
            onClick: toggleLocale,
          },
        ]}
        contentClassName="md:max-w-3xl lg:max-w-6xl"
      />
      <main
        className={cn(
          "mx-auto min-h-dvh max-w-md px-4 pb-10 pt-4 md:max-w-3xl md:px-8 lg:max-w-6xl",
          viewer && "lg:mr-[min(600px,46vw)] lg:max-w-none",
        )}
      >
        <div className="lg:grid lg:grid-cols-[340px_minmax(0,1fr)] lg:items-start lg:gap-8">
          <aside className="lg:sticky lg:top-20">
            {/* Not authorised / no task: nothing from the record, not even the counts */}
            {!gated && (
              <header ref={setCardEl} data-patient-card>
                <PatientCard brief={brief} roleName={roleName} generatedAt={generatedAt} />
              </header>
            )}

            {/* How the sentence was understood: role -> task, as the backend read it */}
            <p className="mt-3 px-1 text-sm text-ink-muted" data-read-as>
              {t("results.readAs")}: <span className="font-medium text-ink">{roleName}</span> →{" "}
              <span className="font-medium text-ink">{brief.taskLabel ?? brief.task}</span>
            </p>

            {!gated && (
              <div className="mt-3">
                <ViewTabs
                  tabs={[
                    { id: "overview", label: t("results.view.overview") },
                    { id: "details", label: t("results.view.details") },
                    { id: "history", label: t("results.view.history") },
                  ]}
                  active={view}
                  onChange={setView}
                  label={t("results.view.label")}
                  panelId="facts-panel"
                />
                <p className="mt-2 px-2 text-xs text-ink-muted" aria-live="polite">
                  {view === "overview"
                    ? t("results.view.overviewHint")
                    : view === "details"
                      ? t("results.view.detailsHint")
                      : t("results.view.historyHint")}
                </p>
              </div>
            )}
          </aside>

          <div className="mt-5 space-y-5 lg:mt-0">
            {notAuthorised && (
              <section
                role="alert"
                data-banner="not_authorised"
                className="rounded-lg border-2 border-contradiction-border bg-contradiction-soft p-5"
              >
                <h2 className="text-[19px] font-semibold text-contradiction-deep">{t("results.notAuthorised.title")}</h2>
                {brief.message && <p className="mt-2 text-[15px] leading-relaxed text-ink">{brief.message}</p>}
              </section>
            )}

            {needsTask && (
              <section
                role="alert"
                data-banner="needs_task"
                className="rounded-lg border-2 border-primary bg-primary/10 p-5"
              >
                <h2 className="text-[19px] font-semibold text-primary-deep">
                  {t(brief.roleMissing ? "results.needsRole.title" : "results.needsTask.title")}
                </h2>
                <p className="mt-2 text-[15px] leading-relaxed text-ink">
                  {t(brief.roleMissing ? "results.needsRole.body" : "results.needsTask.body")}
                </p>
              </section>
            )}

            {mode === "not_applicable" && (
              <section
                role="status"
                data-banner="not_applicable"
                className="rounded-lg border-2 border-dashed border-ink-faint bg-surface p-5"
              >
                <h2 className="text-[19px] font-semibold text-ink">{t("results.notApplicable.title")}</h2>
                {brief.applicabilityNote && (
                  <p className="mt-2 text-[15px] leading-relaxed text-ink">{brief.applicabilityNote}</p>
                )}
                {(brief.applicabilitySources?.length ?? 0) > 0 && (
                  <button
                    type="button"
                    data-source
                    onClick={() => openSources(brief.applicabilitySources!, 0, t("results.notApplicable.title"))}
                    className="mt-3 text-[14px] font-medium text-primary-deep underline underline-offset-2"
                  >
                    {t("results.evidence")}: {brief.applicabilitySources![0].documentLabel}
                  </button>
                )}
              </section>
            )}

            {!gated && brief.routeNote && (
              <section data-banner="fallback" className="rounded-lg border border-primary bg-primary/10 p-4">
                <p className="text-[15px] font-medium text-primary-deep">{brief.routeNote}</p>
                <Suggestions
                  items={brief.suggestions ?? []}
                  onPick={(s) => rerun(brief.roleLabel && !/not authorised/i.test(brief.roleLabel) ? `${brief.roleLabel}, ${s}` : s)}
                />
              </section>
            )}

            {/* Answer first: one line per question the task asks, each with its source */}
            {overview && answerFirst && (
              <section id="facts-panel" aria-labelledby="key-facts-heading" data-key-facts>
                <h2 id="key-facts-heading" className="mb-1 text-sm font-semibold text-ink-muted">
                  {t("results.keyFacts")}
                </h2>
                <KeyFactList lines={keyFacts} onOpenSources={openSources} />
                <button
                  type="button"
                  data-show-more
                  aria-expanded={expanded}
                  aria-controls="details-more"
                  onClick={() => setExpanded((x) => !x)}
                  className="mt-3 w-full rounded-full border border-line bg-surface px-4 py-2.5 text-[14px] font-medium text-primary-deep hover:bg-primary-soft focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary"
                >
                  {expanded ? t("results.showLess") : t("results.showMore")}
                </button>
              </section>
            )}

            {/* Margin note: shown only when the dropped facts are on this screen */}
            {showDetails && blindSpot > 0 && taskConcepts > 0 && droppedOnScreen > 0 && (
              <section data-blind-spot className="border-l-4 border-contradiction pl-4">
                <h2 className="text-[15px] font-semibold text-contradiction-deep">{t("results.blindSpot.title")}</h2>
                <p className="mt-0.5 text-[15px] text-ink">
                  {t("results.blindSpot.body", { n: blindSpot, m: taskConcepts })}
                </p>
              </section>
            )}

            {showDetails && contradictions.length > 0 && (
              <section aria-labelledby="contradictions-heading">
                <h2 id="contradictions-heading" className="mb-3 text-sm font-semibold text-contradiction-deep">
                  {t("results.contradictionsHeading")} ({contradictions.length})
                </h2>
                <div className="space-y-3">
                  {contradictions.map((c) => (
                    <ContradictionCard
                      key={c.id}
                      contradiction={c}
                      onPressSource={(source, all) => openSources(all, all.indexOf(source), c.factLabel)}
                    />
                  ))}
                </div>
              </section>
            )}

            {!gated && view === "details" && (
              <section id="facts-panel" aria-label={t("results.view.details")}>
                <Suspense fallback={<Skeleton className="h-64 w-full rounded-lg" />}>
                  <DetailsView brief={brief} onOpenSources={openSources} />
                </Suspense>
              </section>
            )}

            {!gated && view === "history" && (
              <section id="facts-panel" aria-label={t("results.view.history")}>
                <HistoryLog brief={brief} onOpenSources={openSources} />
              </section>
            )}

            {showDetails && (
              <section id={answerFirst ? "details-more" : "facts-panel"} aria-labelledby="facts-heading">
                <h2 id="facts-heading" className="mb-3 text-sm font-semibold text-ink-muted">
                  {t("results.factsHeading")} ({brief.facts.length})
                </h2>
                {brief.facts.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-ink-faint/60 p-5 text-center text-sm text-ink-muted">
                    {t("results.empty")}
                  </p>
                ) : (
                  <FactList
                    facts={brief.facts}
                    onPressSource={showSource}
                    onPressGuideline={showGuideline}
                  />
                )}
              </section>
            )}

            {showDetails && (brief.alsoRelevant?.length ?? 0) > 0 && (
              <section aria-labelledby="also-heading" data-also-relevant>
                <h2 id="also-heading" className="mb-3 text-sm font-semibold text-ink-muted">
                  {t("results.alsoRelevant")} ({brief.alsoRelevant!.length})
                </h2>
                <AlsoRelevantList facts={brief.alsoRelevant!} onPressSource={showSource} />
              </section>
            )}

            {showDetails && otherIssues > 0 && (
              <p className="text-sm text-ink-muted" data-other-issues>
                {t("results.otherIssues", { n: otherIssues })}
              </p>
            )}
          </div>
        </div>

        {/* read-only statement lives here as plain text (full explanation in Help), not as a banner */}
        <p className="mt-6 text-center text-xs leading-snug text-ink-muted">
          {t("readonly.title")}. {t("app.disclaimer")}
        </p>

        {viewer && (
          <SourceViewer
            key={viewer.citations.map((c) => c.segmentId).join() + viewer.index}
            citations={viewer.citations}
            startIndex={viewer.index}
            title={viewer.title}
            onClose={() => setViewer(null)}
          />
        )}

        <Modal
          open={guideline !== null}
          onOpenChange={(open) => !open && setGuideline(null)}
          title={guideline?.guideline.guidelineName ?? ""}
          description={guideline ? `${t("results.guidelineReason")}: ${guideline.label}` : undefined}
        >
          {guideline && (
            <>
              <p className="rounded-lg bg-canvas p-4 text-[15px] leading-relaxed text-ink">{guideline.guideline.excerpt}</p>
              {guideline.guideline.reference && (
                <p className="mt-3 break-words text-xs text-ink-muted">{guideline.guideline.reference}</p>
              )}
            </>
          )}
        </Modal>
      </main>
    </>
  );
}

// Key facts: one compact row per line: small label, then the answer (value · date · since · Source) as short
// as the letters allow. Never rewritten here: every row is a backend fact, calculation or flag, with its passages.
function KeyFactList({ lines, onOpenSources }: {
  lines: KeyFactLine[];
  onOpenSources: (citations: SourceCitation[], index: number, title: string) => void;
}) {
  const label = (line: KeyFactLine) =>
    line.kind === "safety" ? t("results.keySafety")
      : line.kind === "not_documented" ? t("results.keyNotDocumented")
      : line.kind === "conflict" ? t("results.keyConflict") : line.label;
  return (
    <ul className="divide-y divide-line border-y border-line">
      {lines.map((line) => (
        <li key={line.id} className="px-2 py-2" data-fact={line.id} data-key-fact={line.kind} data-trust={line.trust}>
          <p className={cn("text-[12px] leading-tight",
            line.kind === "conflict" ? "font-medium text-contradiction-deep"
              : line.kind === "not_documented" ? "font-medium text-undocumented" : "text-ink-muted")}>
            {label(line)}
            {line.more > 0 && line.kind !== "conflict" && <span> · {t("results.keyMore", { n: line.more })}</span>}
          </p>
          {line.kind === "safety" ? (
            // one line: "57 years · female · Contrast media allergy (...)", each part with its own source
            <p className="pt-0.5 text-[15px] leading-relaxed">
              {line.rows.map((row, i) => (
                <span key={row.id} className="whitespace-normal">
                  {i > 0 && <span className="text-ink-muted"> · </span>}
                  <span className="font-semibold text-ink"><KeepDoses text={row.text} /></span>
                  {row.sources.length > 0 && (
                    <RowSource row={row} onPress={(r) => onOpenSources(r.sources, 0, label(line))} />
                  )}
                </span>
              ))}
            </p>
          ) : (
          <ul>
            {line.rows.map((row) => (
              <li key={row.id} className="flex items-start gap-2 pt-0.5">
                <p className="min-w-0 flex-1 text-[15px] leading-snug">
                  <span className="font-semibold text-ink"><KeepDoses text={row.text} /></span>
                  {row.date && <span className="text-[13px] text-ink-muted"> · {row.date}</span>}
                  {row.since && <span className="text-[13px] text-ink-muted"> · {t("results.since", { d: row.since })}</span>}
                </p>
                {row.sources.length > 0 && (
                  <RowSource row={row} onPress={(r) => onOpenSources(r.sources, 0, label(line))} />
                )}
              </li>
            ))}
          </ul>
          )}
        </li>
      ))}
    </ul>
  );
}

// P2 "Also relevant": one compact list, one line per need ("label: value · date · Source"); several facts
// become rows, and what the engine collapsed sits behind "+N more". Always visible, no tap needed.
function AlsoRelevantList({ facts, onPressSource }: { facts: Fact[]; onPressSource: (fact: Fact) => void }) {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {facts.map((fact) => {
        const openRow = (row: FactRow) => onPressSource({ ...fact, source: row.sources[0], sources: row.sources });
        const rows = fact.rows ?? [];
        const open = rows.filter((r) => !r.collapsed);
        const label = <span className="text-[13px] text-ink-muted">{fact.label}: </span>;
        let body: ReactNode;
        if (fact.trust === "not_documented" || fact.trust === "not_applicable") {
          body = (
            <p className="text-[15px] leading-snug">
              {label}
              <span className="font-medium text-undocumented">{t(`trust.${fact.trust}`)}</span>
              {fact.trust === "not_applicable" && fact.value ? <span className="text-ink-muted">: {fact.value}</span> : null}
            </p>
          );
        } else if (fact.trend) {
          body = (<>{label}<TrendLine fact={fact} onPressRow={openRow} sparkline={false} /></>);
        } else if (open.length === 1) {
          const r = open[0];
          body = (
            <>
              <div className="flex items-start gap-2">
                <p className="min-w-0 flex-1 text-[14px] leading-snug">
                  {label}
                  <span className="font-semibold text-ink"><KeepDoses text={r.text} /></span>
                  {r.date && <span className="text-[13px] text-ink-muted"> · {r.date}</span>}
                </p>
                {r.sources.length > 0 && <RowSource row={r} onPress={openRow} />}
              </div>
              {rows.length > 1 && <FactRows rows={rows.filter((x) => x !== r)} onPressRow={openRow} className="mt-0" />}
            </>
          );
        } else {
          body = (<>{label}<FactRows rows={rows} onPressRow={openRow} /></>);
        }
        return (
          <li key={fact.id} className="px-3 py-2.5" data-fact={fact.id} data-trust={fact.trust}>
            {body}
          </li>
        );
      })}
    </ul>
  );
}

function Suggestions({ items, onPick }: { items: string[]; onPick: (s: string) => void }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="mb-2 text-sm text-ink-muted">{t("results.tryInstead")}</p>
      <div className="flex flex-wrap gap-2" data-suggestions>
        {items.map((s) => (
          <Chip key={s} selected={false} onClick={() => onPick(s)} className="text-left">
            {s}
          </Chip>
        ))}
      </div>
    </div>
  );
}

// Plain sentences for text to speech: patient, task, contradictions, then every fact with its trust label.
function briefToSpeech(brief: PatientBrief): string {
  if (brief.screenMode === "needs_task") return [sentence(t("results.needsTask.title")), sentence(t("results.needsTask.body"))].join(" ");
  const parts = [sentence(brief.patientLabel), sentence(brief.taskLabel ?? brief.task)];
  if (brief.screenMode === "not_authorised") return [...parts, sentence(brief.message ?? "")].join(" ");
  if (brief.keyFacts?.length) {  // answer first: read what the screen shows by default
    for (const k of brief.keyFacts) parts.push(sentence(`${k.label}: ${k.rows.map((r) => r.text).join("; ")}`));
    return parts.join(" ");
  }
  for (const c of brief.contradictions) parts.push(sentence(`${t("speech.contradiction")}: ${c.factLabel}`));
  for (const f of brief.facts) {
    if (f.trust === "not_documented") parts.push(sentence(`${f.label}: ${t("speech.notDocumented")}`));
    else parts.push(sentence(`${f.label}: ${f.value ?? ""}`), sentence(t(`trust.${f.trust}`)));
  }
  return parts.join(" ");
}

function sentence(text: string): string {
  const trimmed = text.trim();
  return /[.!?…]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}
