import { useNavigate } from "react-router-dom";
import { LanguageSkillIcon } from "@hugeicons/core-free-icons";
import { AppBar } from "@/components/AppBar";
import { getLocale, toggleLocale } from "@/i18n/locale";
import { Faq, type FaqItem } from "@/components/Faq";
import { Notice } from "@/components/ui/Notice";
import { t, type StringKey } from "@/i18n/strings";

// /hilfe: FAQ about what Second Eye shows, what the marks mean and what it never does.

const questions = [1, 2, 3, 4, 5, 6, 7, 8];

export function HelpScreen() {
  // built per render so the language toggle (which remounts the screens) takes effect
  const items: FaqItem[] = questions.map((n) => ({
    id: `q${n}`,
    question: t(`help.q${n}` as StringKey),
    answer: t(`help.a${n}` as StringKey),
  }));
  const navigate = useNavigate();
  // Back returns to wherever help was opened from; opened directly (no history), it goes to the start
  const goBack = () => ((window.history.state as { idx?: number } | null)?.idx ? navigate(-1) : navigate("/"));

  return (
    <>
      <AppBar
        back={{ label: t("action.back"), onClick: goBack }}
        contentClassName="md:max-w-2xl"
        menuActions={[
          {
            id: "language",
            label: t("appbar.language"),
            icon: LanguageSkillIcon,
            text: getLocale() === "en" ? "EN" : "DE",
            onClick: toggleLocale,
          },
        ]}
      />
      <main className="mx-auto max-w-md px-4 pb-12 pt-6 md:max-w-2xl md:px-8 md:pt-10">
        <h1 className="text-[28px] font-semibold leading-tight tracking-tight md:text-4xl">{t("help.title")}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">{t("help.intro")}</p>

        <div className="mt-6">
          <Faq items={items} />
        </div>

        <Notice tone="readonly" title={t("readonly.title")} className="mt-6">
          {t("readonly.body")}
        </Notice>
        <p className="mt-8 text-center text-xs leading-snug text-ink-muted">{t("app.disclaimer")}</p>
      </main>
    </>
  );
}
