// All user-facing UI strings. German first; keep keys stable; the language toggle (Phase 10) swaps values.
// Copy rule: factual only ("Erforderliche Prüfungen", "Verifiziert", "Nicht dokumentiert"): never advisory.

export const strings = {
  "app.name": "Second Look",
  "appbar.home": "Second Look: zur Startseite",
  "appbar.menu": "Weitere Aktionen",
  "appbar.help": "Hilfe",
  "appbar.newRequest": "Neue Anfrage",

  // Error pages
  "error.404.title": "Seite nicht gefunden",
  "error.404.body": "Diese Adresse gibt es in Second Look nicht. Patientendaten sind davon nicht betroffen.",
  "error.crash.code": "Fehler",
  "error.crash.title": "Diese Ansicht konnte nicht angezeigt werden",
  "error.crash.body": "Ein technischer Fehler ist aufgetreten. Es wurden keine Daten geändert.",
  "error.home": "Zur Startseite",
  "error.reload": "Neu laden",

  // Help / FAQ
  "help.title": "Häufige Fragen",
  "help.intro": "Wie Second Look arbeitet, was die Markierungen bedeuten und was die App nicht tut.",
  "help.q1": "Was zeigt Second Look?",
  "help.a1":
    "Für eine Rolle und eine Aufgabe zeigt Second Look nur die Angaben aus den Patientendokumenten, die für diese Aufgabe erforderlich sind. Jede Angabe verweist auf ihre Quellstelle.",
  "help.q2": "Woher stammen die Angaben?",
  "help.a2":
    "Aus den Arztbriefen und Befunden der Patientin bzw. des Patienten. „Quelle“ öffnet den genauen Satz oder die Tabellenzeile, aus der eine Angabe stammt.",
  "help.q3": "Was bedeuten Verifiziert, Prüfung erforderlich und Nicht dokumentiert?",
  "help.a3":
    "Verifiziert: wörtlich in einem Dokument gefunden. Prüfung erforderlich: von der KI abgeleitet und nicht wörtlich bestätigt. Nicht dokumentiert: in keinem Dokument gefunden. Second Look ergänzt fehlende Angaben nie.",
  "help.q4": "Was ist ein Widerspruch?",
  "help.a4":
    "Zwei Dokumente machen zur selben Sache unvereinbare Angaben, zum Beispiel zu Allergien. Beide Stellen werden nebeneinander gezeigt. Welche Angabe zutrifft, entscheidet Second Look nicht.",
  "help.q5": "Kann ich Daten ändern?",
  "help.a5":
    "Nein. Second Look ändert keine Arztbriefe, Befunde oder Notizen. Über „Melden“ lässt sich ein Fehler melden; jede Meldung wird geprüft.",
  "help.q6": "Gibt Second Look Diagnosen oder Empfehlungen?",
  "help.a6":
    "Nein. Gezeigt werden nur dokumentierte Angaben und daraus berechnete Werte, etwa eine Gewichtsänderung. Es gibt keine Diagnosen, keine Therapieempfehlungen und keine Vorhersagen.",
  "help.q7": "Was zeigen Übersicht, Verlauf und Dashboard?",
  "help.a7":
    "Übersicht: die aktuellen Werte. Verlauf: frühere Werte, wo dokumentiert. Dashboard: berechnete Änderungen, den Abgleich von notiertem und berechnetem BMI und Blutdruckvergleiche, jeweils mit beiden Quellen.",
  "help.q8": "Wie funktioniert Vorlesen?",
  "help.a8":
    "Im Modus „Vorlesen“ liest der Browser die Übersicht vor. Das geht nur mit einer deutschen Stimme auf dem Gerät; Stimmen, die direkt auf dem Gerät laufen, werden bevorzugt.",
  "readonly.title": "Nur Lesen: Second Look ändert keine Daten",
  "readonly.body":
    "Arztbriefe, Befunde und Notizen bleiben unverändert. Fehler lassen sich nur melden; jede Meldung wird geprüft.",
  "app.disclaimer": "Keine Diagnose- oder Therapieempfehlung. Alle Angaben verweisen auf ihre Quelle.",

  // Start screen (role chips + task bar)
  "start.title": "Welche Aufgabe steht an?",
  "start.subtitle": "Rolle wählen, Aufgabe eingeben. Angezeigt werden nur die dafür erforderlichen Fakten, jeweils mit Quelle.",
  "start.roleHeading": "Rolle",
  "start.suggestionsHeading": "Häufige Aufgaben",
  "start.roleMissing": "Zuerst eine Rolle wählen.",

  // Task bar
  "bar.placeholder.display": "Aufgabe eingeben",
  "bar.placeholder.speak": "Aufgabe zum Vorlesen",
  "bar.mode.switchLabel": "Ergebnis vorlesen",
  "bar.mode.display": "Ergebnis wird angezeigt.",
  "bar.mode.speak": "Ergebnis wird angezeigt und vorgelesen.",
  "bar.mode.speakUnsupported": "Keine deutsche Stimme auf diesem Gerät verfügbar. Ergebnis wird nur angezeigt.",
  "bar.send": "Patientenübersicht abrufen",

  "role.anaesthetist.name": "Anästhesie",
  "role.anaesthetist.description": "Prämedikation / präoperative Prüfung",
  "role.pharmacist.name": "Pharmazie",
  "role.pharmacist.description": "Medikationsanalyse",
  "role.surgeon.name": "Chirurgie",
  "role.surgeon.description": "OP-Planung",
  "role.gp.name": "Hausarztpraxis",
  "role.gp.description": "Nachsorge",

  "task.anaesthetist.breast": "Prämedikation: Mamma-OP",
  "task.anaesthetist.hip": "Prämedikation: Hüft-TEP",
  "task.anaesthetist.general": "Prämedikation: allgemein",
  "task.pharmacist.polypharmacy": "Medikationsanalyse: Polypharmazie",
  "task.pharmacist.renal": "Dosisprüfung: Nierenfunktion",
  "task.pharmacist.admission": "Aufnahmemedikation abgleichen",
  "task.surgeon.hip": "OP-Planung: Hüft-TEP",
  "task.surgeon.breast": "OP-Planung: Mamma-OP",
  "task.surgeon.hernia": "OP-Planung: Leistenhernie",
  "task.gp.discharge": "Nachsorge: nach Krankenhausaufenthalt",
  "task.gp.chronic": "Verlaufskontrolle: chronische Erkrankung",
  "task.gp.medication": "Medikationsplan aktualisieren",

  // Trust tiers
  "trust.verified": "Verifiziert",
  "trust.ai_inferred": "Prüfung erforderlich",
  "trust.not_documented": "Nicht dokumentiert",

  // Generic actions
  "action.source": "Quelle anzeigen",
  "action.guideline": "Leitlinie anzeigen",
  "action.flag": "Melden",
  "action.export": "Exportieren",
  "action.close": "Schließen",
  "action.submitFlag": "Meldung senden",
  "action.cancel": "Abbrechen",
  "action.retry": "Erneut versuchen",
  "action.back": "Zurück",

  // Misc labels
  "label.contradiction": "Widerspruch",
  "label.severity.low": "Niedrig",
  "label.severity.medium": "Mittel",
  "label.severity.high": "Hoch",

  // Loading
  "loading.title": "Patientenübersicht wird erstellt …",
  "loading.error.title": "Patientenübersicht konnte nicht geladen werden",
  "loading.error.timeout": "Keine Antwort innerhalb von 10 Sekunden.",
  "loading.error.generic": "Beim Abrufen der Daten ist ein Fehler aufgetreten.",

  // Results
  "results.generatedAt": "Stand",
  "results.contradictionsHeading": "Widersprüche zwischen Dokumenten",
  "results.factsHeading": "Erforderliche Angaben",
  "results.empty": "Für diese Aufgabe wurden keine Angaben gefunden.",
  "results.source": "Quelle",
  "results.guideline": "Leitlinie",
  "results.patientRecord": "Patientenakte",
  "results.guidelineReason": "Warum diese Angabe erforderlich ist",
  "results.readAloud": "Vorlesen",
  "results.stopReading": "Vorlesen stoppen",
  "results.noGermanVoice": "Vorlesen nicht verfügbar: keine deutsche Stimme auf diesem Gerät",
  "results.language": "Sprache",
  "results.comingSoon": "Folgt in einem späteren Schritt.",
  "results.flagTitle": "Angabe melden",
  "results.severity": "Schweregrad",
  "results.view.label": "Ansicht",
  "results.view.overview": "Übersicht",
  "results.view.history": "Verlauf",
  "results.view.historyAvailable": "Verlauf für {n} von {m} Angaben verfügbar.",
  "results.view.historyNone": "Für keine Angabe sind Verlaufswerte dokumentiert.",
  "results.view.overviewHint": "Aktuelle Werte. Verlauf zeigt frühere Werte, wo dokumentiert.",
  "results.view.dashboard": "Dashboard",
  "results.view.dashboardHint": "Berechnete Änderungen aus dokumentierten Werten. Rechnungen, keine Diagnosen.",
  "results.sources": "Quellen",

  // Dashboard level (factual, no scores, no predictions, no advice)
  "dash.title": "Kennzahlen",
  "dash.recordsThrough": "Unterlagen bis {date}",
  "dash.loading": "Kennzahlen werden geladen …",
  "dash.error": "Kennzahlen konnten nicht geladen werden.",
  "dash.empty": "Für diese Patientin bzw. diesen Patienten sind keine Messwerte oder Dosisänderungen dokumentiert.",
  "dash.proof.title": "Belegte Angaben",
  "dash.proof.ring": "mit Quelle",
  "dash.proof.text": "{n} von {m} Angaben sind mit einer Quellstelle belegt. Entfernt, weil nicht im Brief auffindbar: {r}.",
  "dash.tiles": "Dokumentierte Änderungen",
  "dash.tile.weight": "Gewicht",
  "dash.tile.bmi": "BMI berechnet",
  "dash.tile.dose": "{drug} verordnet",
  "dash.tile.bp": "Blutdruck: {label}",
  "dash.tile.compare": "{from} → {to}",
  "dash.sourcesFor": "Quellen: {label}",
  "dash.weight.title": "Gewicht",
  "dash.weight.unit": "kg",
  "dash.bmi.title": "BMI: notiert und berechnet",
  "dash.bmi.recorded": "Notiert im Brief",
  "dash.bmi.calculated": "Berechnet aus Gewicht und Größe",
  "dash.bmi.agrees": "Stimmt überein",
  "dash.bmi.differs": "Abweichung {diff}",
  "dash.bmi.notRecorded": "Kein BMI notiert",
  "dash.bmi.note":
    "Abweichung = notiert minus berechnet, in kg/m². Toleranz {tol} kg/m² zur Datenqualität, kein klinischer Grenzwert. Eine Abweichung zeigt nicht, welcher Eingabewert falsch ist.",
  "dash.bp.title": "Blutdruck-Vergleiche",
  "dash.bp.unit": "mmHg",
  "dash.bp.percent": "Systolisch {sys} · Diastolisch {dia}",
  "dash.dated.title": "Datierte Befunde ohne Verlauf",
  "dash.notes.title": "Dokumentierter Kontext",

  // Patient card
  "patient.id": "ID",
  "patient.details": "Details",
  "patient.openDetails": "Patientendetails öffnen",
  "patient.closeDetails": "Patientendetails schließen",
  "patient.trustSummary": "Angaben nach Vertrauensstufe",
  "patient.stats": "Messwerte im Verlauf",
  "patient.noStats": "Keine Verlaufswerte in den Dokumenten.",
  "patient.documents": "Quelldokumente",
  "patient.factSingular": "Angabe",
  "patient.factPlural": "Angaben",
  "patient.inContradiction": "Widerspruch",
  "patient.trend": "Verlauf",

  // Read-aloud sentences
  "speech.contradiction": "Widerspruch",
  "speech.notDocumented": "nicht dokumentiert",

  // Styleguide (dev only)
  "dev.styleguide.title": "Styleguide",
} as const;

export type StringKey = keyof typeof strings;

// Optional vars fill {placeholders}, so word order stays in the translation: t("x", { n: 1, m: 5 })
export function t(key: StringKey, vars?: Record<string, string | number>): string {
  const text: string = strings[key];
  return vars ? text.replace(/\{(\w+)\}/g, (match, name) => String(vars[name] ?? match)) : text;
}
