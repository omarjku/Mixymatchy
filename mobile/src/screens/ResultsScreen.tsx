import { useEffect, useMemo, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft01Icon, Download04Icon, StopCircleIcon, VolumeHighIcon } from "@hugeicons/core-free-icons";
import { ContradictionCard } from "@/components/ContradictionCard";
import { FactCard } from "@/components/FactCard";
import { PatientCard } from "@/components/PatientCard";
import { hasHistory } from "@/components/ValueHistory";
import { ViewTabs } from "@/components/ViewTabs";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
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
  | { kind: "info"; title: string };

export function ResultsScreen() {
  const navigate = useNavigate();
  const state = useLocation().state as ResultsState | null;
  const voiceAvailable = useGermanVoiceAvailable();
  const [speaking, setSpeaking] = useState(false);
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [view, setView] = useState<"overview" | "history">("overview");

  const brief = state?.brief;
  const historyCount = brief?.facts.filter((f) => f.trust !== "not_documented" && hasHistory(f)).length ?? 0;
  const speechText = useMemo(() => (brief ? briefToSpeech(brief) : ""), [brief]);

  const speechEvents = useMemo(
    () => ({ onStart: () => setSpeaking(true), onEnd: () => setSpeaking(false) }),
    [],
  );

  // Auto read-aloud when the clinician chose "Vorlesen" on the start screen
  useEffect(() => {
    if (!state?.readAloud || !voiceAvailable) return;
    speak(speechText, speechEvents);
    return () => stopSpeaking();
  }, [state?.readAloud, voiceAvailable, speechText, speechEvents]);

  // Stop any reading when leaving the screen
  useEffect(() => () => stopSpeaking(), []);

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
    <main className="mx-auto min-h-dvh max-w-md px-4 pb-10 pt-[env(safe-area-inset-top)]">
      <div className="sticky top-0 z-10 -mx-4 flex h-14 items-center justify-between bg-canvas px-2">
        <Button variant="icon" icon={ArrowLeft01Icon} label={t("action.back")} onClick={() => navigate("/")} />
        <div className="flex items-center">
          <Button
            variant="icon"
            icon={speaking ? StopCircleIcon : VolumeHighIcon}
            label={
              voiceAvailable ? (speaking ? t("results.stopReading") : t("results.readAloud")) : t("results.noGermanVoice")
            }
            aria-pressed={speaking}
            disabled={!voiceAvailable}
            onClick={toggleReading}
            className={speaking ? "bg-primary-soft text-primary-deep" : "disabled:opacity-40"}
          />
          <Button
            variant="icon"
            icon={Download04Icon}
            label={t("action.export")}
            onClick={() => comingSoon(t("action.export"))}
          />
          <button
            type="button"
            onClick={() => comingSoon(t("results.language"))}
            aria-label={`${t("results.language")}: Deutsch`}
            className="ml-1 h-9 rounded-full border border-line px-3 text-xs font-semibold text-ink-muted hover:border-primary/60 hover:text-primary-deep"
          >
            DE
          </button>
        </div>
      </div>

      <header className="mt-2">
        <PatientCard brief={brief} roleName={roleName} generatedAt={generatedAt} />
      </header>

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
              ? t("results.view.historyAvailable", { n: historyCount, m: brief.facts.length })
              : t("results.view.historyNone")}
        </p>
      </div>

      {brief.contradictions.length > 0 && (
        <section aria-labelledby="contradictions-heading" className="mt-6">
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

      <section id="facts-panel" aria-labelledby="facts-heading" className="mt-6">
        <h2 id="facts-heading" className="mb-3 text-sm font-semibold text-ink-muted">
          {t("results.factsHeading")} ({brief.facts.length})
        </h2>
        {brief.facts.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-ink-faint/60 p-5 text-center text-sm text-ink-muted">
            {t("results.empty")}
          </p>
        ) : (
          <div className="space-y-3">
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

      <p className="mt-8 text-center text-xs leading-snug text-ink-muted">{t("app.disclaimer")}</p>

      <Modal
        open={sheet !== null}
        onOpenChange={(open) => !open && setSheet(null)}
        title={sheetTitle(sheet)}
        description={sheetDescription(sheet)}
      >
        {sheet?.kind === "source" && <Excerpt text={sheet.source.excerpt} />}
        {sheet?.kind === "guideline" && (
          <>
            <Excerpt text={sheet.guideline.excerpt} />
            {sheet.guideline.reference && (
              <p className="mt-3 break-words text-xs text-ink-muted">{sheet.guideline.reference}</p>
            )}
          </>
        )}
        {sheet?.kind === "info" && <p className="text-[15px] text-ink-muted">{t("results.comingSoon")}</p>}
      </Modal>
    </main>
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

function sheetDescription(sheet: Sheet | null): string | undefined {
  if (sheet?.kind === "source") return t("results.patientRecord");
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
