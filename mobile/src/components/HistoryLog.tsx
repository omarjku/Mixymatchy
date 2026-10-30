import { parseGermanNumber } from "@/components/Sparkline";
import { intlLocale } from "@/i18n/locale";
import { t } from "@/i18n/strings";
import { formatNumber } from "@/lib/stats";
import type { Fact, PatientBrief, SourceCitation } from "@/types/fact";
import { KeepDoses } from "@/components/ui/KeepDoses";

// "History" level of the results: a plain log of every dated entry in the brief, newest first.
// Date | what | value as the letter wrote it | Source. No charts, no status marks, no calculations:
// changes and charts live in Details. Entries without a date sit at the end.

type OpenSources = (citations: SourceCitation[], index: number, title: string) => void;

interface Entry {
  key: string;
  time: number | null; // null: the letter gives no date
  date: string;
  label: string;
  value: string;
  sources: SourceCitation[];
}

// Dates are parsed as UTC midnight, so they are formatted in UTC too (no day shift west of Greenwich)
const dateFormat = () =>
  new Intl.DateTimeFormat(intlLocale(), { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });

// Brief dates come as ISO (history) or day-first dd.mm.yyyy / dd/mm/yyyy (rows, trend points; German / English)
function parseDate(value: string): number | null {
  const dayFirst = /^(\d{1,2})[./](\d{1,2})[./](\d{4})$/.exec(value.trim());
  const time = dayFirst ? Date.UTC(+dayFirst[3], +dayFirst[2] - 1, +dayFirst[1]) : Date.parse(value);
  return Number.isNaN(time) ? null : time;
}

function entriesOf(fact: Fact): Entry[] {
  if (fact.trust === "not_documented" || fact.trust === "not_applicable") return [];
  const out: Entry[] = [];
  const seen = new Set<string>();
  const all = fact.sources ?? (fact.source ? [fact.source] : []);
  const add = (date: string | undefined, value: string, sources: SourceCitation[], id: string) => {
    const time = date ? parseDate(date) : null;
    const key = `${time ?? date}|${value}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      key: `${fact.id}:${id}`,
      time,
      date: time === null ? "" : dateFormat().format(new Date(time)),
      label: fact.label,
      value,
      sources,
    });
  };

  // Measured series: one entry per reading. A passage per reading when the brief has one for each,
  // otherwise only the latest reading links to the fact's source.
  const unit = fact.value?.replace(/^[-\d.,\s→]+/, "").split(" ")[0] ?? "";
  const history = fact.history ?? [];
  const perReading = all.length === history.length;
  history.forEach((h, i) => {
    const u = h.unit ?? unit;
    // readings are raw document numbers ("1,0"): written in the UI language's format, like Details
    const n = parseGermanNumber(h.value);
    const shown = n === null ? h.value : formatNumber(n, (h.value.split(/[.,]/)[1] ?? "").length);
    const sources = perReading ? [all[i]] : i === history.length - 1 && fact.source ? [fact.source] : [];
    add(h.date, u ? `${shown} ${u}` : shown, sources, `h${i}`);
  });
  if (history.length === 0) {
    fact.trend?.points.forEach((p, i) => add(p.date, p.value, all.length === fact.trend!.points.length ? [all[i]] : [], `t${i}`));
  }

  // Documented statements (calculated rows are not log entries) and older values a newer letter replaced
  for (const row of [...(fact.superseded ?? []), ...(fact.rows ?? [])]) {
    if (!row.computed) add(row.date, row.text, row.sources, row.id);
  }

  // A plain single value with no date in the brief: listed under "No date" at the end
  if (out.length === 0 && fact.value) add(undefined, fact.value, all, "value");
  return out;
}

export function HistoryLog({ brief, onOpenSources }: { brief: PatientBrief; onOpenSources: OpenSources }) {
  const facts = [...brief.facts, ...(brief.alsoRelevant ?? [])];
  const entries = facts.flatMap(entriesOf);
  const dated = entries.filter((e) => e.time !== null).sort((a, b) => b.time! - a.time!);
  const undated = entries.filter((e) => e.time === null);

  if (entries.length === 0) {
    return <p className="border-y border-line px-3 py-5 text-center text-sm text-ink-muted">{t("history.empty")}</p>;
  }

  return (
    <div className="space-y-7">
      {dated.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-ink-muted">
            {t("results.view.history")} ({dated.length})
          </h2>
          <LogList entries={dated} onOpenSources={onOpenSources} />
        </section>
      )}
      {undated.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-ink-muted">
            {t("history.undated")} ({undated.length})
          </h2>
          <LogList entries={undated} onOpenSources={onOpenSources} />
        </section>
      )}
    </div>
  );
}

function LogList({ entries, onOpenSources }: { entries: Entry[]; onOpenSources: OpenSources }) {
  return (
    <ol className="divide-y divide-line border-y border-line">
      {entries.map((e, i) => (
        <li key={e.key} className="grid grid-cols-[5.75rem_minmax(0,1fr)_auto] items-baseline gap-x-3 px-3 py-2.5">
          {/* date only on the first entry of a day: reads as a log, not a repeated column */}
          <span className="text-[13px] text-ink-muted tabular-nums">
            {e.date && e.date !== entries[i - 1]?.date ? e.date : ""}
          </span>
          <p className="min-w-0 text-[15px] leading-snug">
            <span className="text-ink-muted">{e.label}: </span>
            <span className="font-medium text-ink"><KeepDoses text={e.value} /></span>
          </p>
          {e.sources.length > 0 ? (
            <button
              type="button"
              data-source
              onClick={() => onOpenSources(e.sources, 0, e.label)}
              className="-my-1 inline-flex min-h-8 items-center whitespace-nowrap rounded px-1 text-[13px] font-medium text-primary-deep underline-offset-2 hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary"
            >
              {t("results.source")}
            </button>
          ) : (
            <span />
          )}
        </li>
      ))}
    </ol>
  );
}
