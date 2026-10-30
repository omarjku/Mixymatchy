import { parseGermanNumber, Sparkline } from "@/components/Sparkline";
import { intlLocale } from "@/i18n/locale";
import { t } from "@/i18n/strings";
import type { Fact } from "@/types/fact";

// History of one measured fact: trend line plus every dated value written out (the values, not the line,
// are what a clinician reads). Used by the patient card's stats panel and by fact cards in "Verlauf" view.

export function hasHistory(fact: Fact): boolean {
  return Boolean(fact.isTimeSeries && fact.history && fact.history.length > 0);
}

export function ValueHistory({ fact }: { fact: Fact }) {
  const history = fact.history ?? [];
  const numbers = history.map((h) => parseGermanNumber(h.value)).filter((n): n is number => n !== null);
  // unit comes from the latest value ("1,3 mg/dl" -> "mg/dl"); history entries carry the number only
  const unit = fact.value?.replace(/^[-\d.,\s]+/, "").trim() ?? "";
  const dateFormat = new Intl.DateTimeFormat(intlLocale(), { day: "2-digit", month: "2-digit", year: "numeric" });

  return (
    <div className="mt-3">
      {numbers.length === history.length && <Sparkline values={numbers} className="h-12 w-full" />}
      <table className="mt-2 w-full text-xs">
        <caption className="sr-only">
          {t("patient.trend")}: {fact.label}
        </caption>
        <tbody>
          {history.map((h, i) => (
            <tr key={h.date} className={i === history.length - 1 ? "font-semibold" : undefined}>
              <td className="py-0.5 text-ink-muted">
                <time dateTime={h.date}>{dateFormat.format(new Date(h.date))}</time>
              </td>
              <td className="py-0.5 text-right font-mono text-ink">
                {h.value} {unit}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
