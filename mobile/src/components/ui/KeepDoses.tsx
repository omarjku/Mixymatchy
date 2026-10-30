import { Fragment } from "react";

// Dosing schedules like "1-0-1" or "1/2-0-0-1" never break across lines (a browser breaks after a hyphen,
// which turns "1-0-1" into "1-0-" + "1": a different instruction at a glance).
const dose = /(\d+(?:[.,/]\d+)?(?:-\d+(?:[.,/]\d+)?){2,3})/;

export function KeepDoses({ text }: { text: string }) {
  const parts = text.split(dose);
  if (parts.length === 1) return <>{text}</>;
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <span key={i} className="whitespace-nowrap">
            {part}
          </span>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}
