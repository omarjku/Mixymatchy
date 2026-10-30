import { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Add01Icon, LanguageSkillIcon, StopCircleIcon, VolumeHighIcon } from "@hugeicons/core-free-icons";
import { AppBar } from "@/components/AppBar";
import { ContradictionCard } from "@/components/ContradictionCard";
import { FactCard } from "@/components/FactCard";
import { PatientCard } from "@/components/PatientCard";
import { SourceViewer } from "@/components/SourceViewer";
import { hasHistory } from "@/components/ValueHistory";
import { ViewTabs } from "@/components/ViewTabs";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { Notice } from "@/components/ui/Notice";
import { roles } from "@/data/roles";
import { intlLocale, toggleLocale, useLocale } from "@/i18n/locale";
import { t } from "@/i18n/strings";
import { getResults } from "@/lib/session";
import { speak, stopSpeaking, useVoiceAvailable } from "@/lib/speech";
import { cn } from "@/lib/utils";
import type { Fact, GuidelineCitation, PatientBrief, SourceCitation } from "@/types/fact";
import type { BriefRequest } from "@/types/request";

// Results: patient + how the request was read, banners (not authorised / not applicable / task not
// recognised), the record's contradictions, the facts the task needs (P1), "Also relevant" (P2, always
// visible), documentation notes and open items. Every source link opens the original letter.

type View = "overview" | "history";
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

  const brief = state?.brief;
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
  const generatedAt = new Intl.DateTimeFormat(intlLocale(), { dateStyle: "medium" }).format(new Date(brief.generatedAt));
  const mode = brief.screenMode ?? "task";
  const notAuthorised = mode === "not_authorised";
  const stats = brief.stats ?? {};
  const allFacts = [...brief.facts, ...(brief.alsoRelevant ?? [])];
  const historyCount = allFacts.filter((f) => f.trust !== "not_documented" && hasHistory(f)).length;

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
  const notes = brief.contradictions.filter((c) => c.tier === "documentation_note");
  const gaps = brief.gaps ?? [];
  const droppedOnScreen = gaps.filter((g) => g.kind === "dropped").length;
  const blindSpot = stats.blind_spot ?? 0;
  const taskConcepts = stats.task_concepts ?? 0;
  const otherIssues = stats.other_record_issues ?? 0;
  const factCard = (fact: Fact) => (
    <FactCard
      key={fact.id}
      fact={fact}
      showHistory={view === "history"}
      onPressSource={showSource}
      onPressGuideline={showGuideline}
    />
  );

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
            {/* Not authorised: nothing from the record, not even the counts */}
            {!notAuthorised && (
              <header ref={setCardEl}>
                <PatientCard brief={brief} roleName={roleName} generatedAt={generatedAt} />
              </header>
            )}

            {/* How the sentence was understood: role -> task, as the backend read it */}
            <p className="mt-3 px-1 text-sm text-ink-muted" data-read-as>
              {t("results.readAs")}: <span className="font-medium text-ink">{roleName}</span> →{" "}
              <span className="font-medium text-ink">{brief.taskLabel ?? brief.task}</span>
            </p>

            <Notice tone="readonly" title={t("readonly.title")} className="mt-4">
              {t("readonly.body")}
            </Notice>

            {!notAuthorised && (
              <div className="mt-4">
                <ViewTabs
                  tabs={[
                    { id: "overview", label: t("results.view.overview") },
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
                    : historyCount > 0
                      ? t("results.view.historyAvailable", { n: historyCount, m: allFacts.length })
                      : t("results.view.historyNone")}
                </p>
              </div>
            )}
          </aside>

          <div className="mt-6 space-y-6 lg:mt-0">
            {notAuthorised && (
              <section
                role="alert"
                data-banner="not_authorised"
                className="rounded-2xl border-2 border-contradiction-border bg-contradiction-soft p-5"
              >
                <h2 className="text-[19px] font-semibold text-contradiction-deep">{t("results.notAuthorised.title")}</h2>
                {brief.message && <p className="mt-2 text-[15px] leading-relaxed text-ink">{brief.message}</p>}
                <Suggestions items={brief.suggestions ?? []} onPick={rerun} />
              </section>
            )}

            {mode === "not_applicable" && (
              <section
                role="status"
                data-banner="not_applicable"
                className="rounded-2xl border-2 border-dashed border-ink-faint bg-surface p-5"
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

            {!notAuthorised && brief.routeNote && (
              <section data-banner="fallback" className="rounded-2xl border border-primary bg-primary/10 p-4">
                <p className="text-[15px] font-medium text-primary-deep">{brief.routeNote}</p>
                <Suggestions
                  items={brief.suggestions ?? []}
                  onPick={(s) => rerun(brief.roleLabel && !/not authorised/i.test(brief.roleLabel) ? `${brief.roleLabel}, ${s}` : s)}
                />
              </section>
            )}

            {/* Margin note: shown only when the dropped facts are on this screen */}
            {!notAuthorised && blindSpot > 0 && taskConcepts > 0 && droppedOnScreen > 0 && (
              <section data-blind-spot className="border-l-4 border-contradiction pl-4">
                <h2 className="text-[15px] font-semibold text-contradiction-deep">{t("results.blindSpot.title")}</h2>
                <p className="mt-0.5 text-[15px] text-ink">
                  {t("results.blindSpot.body", { n: blindSpot, m: taskConcepts })}
                </p>
              </section>
            )}

            {contradictions.length > 0 && (
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

            {!notAuthorised && (
              <section id="facts-panel" aria-labelledby="facts-heading">
                <h2 id="facts-heading" className="mb-3 text-sm font-semibold text-ink-muted">
                  {t("results.factsHeading")} ({brief.facts.length})
                </h2>
                {brief.facts.length === 0 ? (
                  <p className="rounded-2xl border border-dashed border-ink-faint/60 p-5 text-center text-sm text-ink-muted">
                    {t("results.empty")}
                  </p>
                ) : (
                  <div className={cn("grid gap-3 md:grid-cols-2", viewer && "lg:grid-cols-1")}>{brief.facts.map(factCard)}</div>
                )}
              </section>
            )}

            {!notAuthorised && (brief.alsoRelevant?.length ?? 0) > 0 && (
              <section aria-labelledby="also-heading" data-also-relevant>
                <h2 id="also-heading" className="mb-3 text-sm font-semibold text-ink-muted">
                  {t("results.alsoRelevant")} ({brief.alsoRelevant!.length})
                </h2>
                <div className={cn("grid gap-3 md:grid-cols-2", viewer && "lg:grid-cols-1")}>{brief.alsoRelevant!.map(factCard)}</div>
              </section>
            )}

            {notes.length > 0 && (
              <section aria-labelledby="notes-heading">
                <h2 id="notes-heading" className="mb-3 text-sm font-semibold text-ink-muted">
                  {t("results.notesHeading")} ({notes.length})
                </h2>
                <div className="space-y-3">
                  {notes.map((c) => (
                    <ContradictionCard
                      key={c.id}
                      contradiction={c}
                      onPressSource={(source, all) => openSources(all, all.indexOf(source), c.factLabel)}
                    />
                  ))}
                </div>
              </section>
            )}

            {gaps.length > 0 && (
              <section aria-labelledby="gaps-heading">
                <h2 id="gaps-heading" className="mb-3 text-sm font-semibold text-ink-muted">
                  {t("results.gapsHeading")} ({gaps.length})
                </h2>
                <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
                  {gaps.map((gap) => (
                    <li key={gap.id} className="p-4">
                      <p className="text-xs font-medium text-ink-muted">{t(`results.gap.${gap.kind}`)}</p>
                      <p className="mt-0.5 text-[15px] font-semibold text-ink">{gap.title}</p>
                      {gap.explanation && <p className="mt-0.5 text-[14px] text-ink-muted">{gap.explanation}</p>}
                      {gap.sources.length > 0 && (
                        <button
                          type="button"
                          data-source
                          onClick={() => openSources(gap.sources, 0, gap.title)}
                          className="mt-2 text-[13px] font-medium text-primary-deep underline underline-offset-2"
                        >
                          {t("results.source")}
                          {gap.sources.length > 1 ? ` (${gap.sources.length})` : ""}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {!notAuthorised && otherIssues > 0 && (
              <p className="text-sm text-ink-muted" data-other-issues>
                {t("results.otherIssues", { n: otherIssues })}
              </p>
            )}
          </div>
        </div>

        <p className="mt-8 text-center text-xs leading-snug text-ink-muted">{t("app.disclaimer")}</p>

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
              <p className="rounded-xl bg-canvas p-4 text-[15px] leading-relaxed text-ink">{guideline.guideline.excerpt}</p>
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
  const parts = [sentence(brief.patientLabel), sentence(brief.taskLabel ?? brief.task)];
  if (brief.screenMode === "not_authorised") return [...parts, sentence(brief.message ?? "")].join(" ");
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
