import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { LanguageSkillIcon } from "@hugeicons/core-free-icons";
import { AppBar } from "@/components/AppBar";
import { TaskBar } from "@/components/TaskBar";
import { t } from "@/i18n/strings";
import { unlockSpeech, useVoiceAvailable } from "@/lib/speech";
import { toggleLocale, useLocale } from "@/i18n/locale";
import type { BriefRequest, DeliveryMode } from "@/types/request";

// Start screen: ONE free-text field ("Who are you and what do you need?") and the send button. No role
// chips and no example chips: the sentence goes to the backend exactly as typed, which reads role and task.
// Bar sits at the bottom, within thumb reach, like a chat composer.

export function RoleTaskSelectScreen() {
  const navigate = useNavigate();
  const [task, setTask] = useState("");
  const [mode, setMode] = useState<DeliveryMode>("display");

  const trimmedTask = task.trim();
  const canSubmit = trimmedTask.length > 0;
  const speechAvailable = useVoiceAvailable();
  const locale = useLocale();

  function submit() {
    if (!trimmedTask) return;
    const readAloud = mode === "speak" && speechAvailable;
    // must run inside this tap, or iOS Safari blocks the speech that starts later on the results screen
    if (readAloud) unlockSpeech();
    const request: BriefRequest = { role: "other", task: trimmedTask, readAloud };
    navigate("/loading", { state: request });
  }

  let caption = mode === "speak" ? t("bar.mode.speak") : t("bar.mode.display");
  if (mode === "speak" && !speechAvailable) caption = t("bar.mode.speakUnsupported");

  return (
    // Phone: bar pinned to the bottom (thumb reach). Tablet/desktop: one centered composer column.
    <>
    <AppBar
      contentClassName="md:max-w-2xl"
      menuActions={[
        {
          id: "language",
          label: t("appbar.language"),
          icon: LanguageSkillIcon,
          text: locale === "en" ? "EN" : "DE",
          onClick: toggleLocale,
        },
      ]}
    />
    <main className="mx-auto flex min-h-[calc(100dvh-3.5rem-env(safe-area-inset-top))] max-w-md flex-col px-4 md:max-w-2xl md:px-8">

      <div className="flex flex-1 flex-col md:justify-center md:pb-[12vh]">
        <section className="mt-6 md:mt-0 md:text-center">
          <h1 className="text-[28px] font-semibold leading-tight tracking-tight md:text-4xl">{t("start.title")}</h1>
          <p className="mt-2 text-[15px] leading-relaxed text-ink-muted md:mx-auto md:max-w-lg">
            {t("start.subtitle")}
          </p>
        </section>

        <div className="sticky bottom-0 -mx-4 mt-auto bg-canvas px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-6 md:static md:mx-0 md:mt-8 md:px-0 md:pb-0">
          <TaskBar
            value={task}
            onValueChange={setTask}
            mode={mode}
            onModeChange={setMode}
            onSubmit={submit}
            canSubmit={canSubmit}
          />
          <p className="mt-2 px-4 text-xs text-ink-muted" aria-live="polite">
            {caption}
          </p>
          <p className="mt-4 text-center text-xs leading-snug text-ink-muted">{t("app.disclaimer")}</p>
        </div>
      </div>
    </main>
    </>
  );
}
