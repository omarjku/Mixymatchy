import { useState } from "react";
import { Book02Icon, Download04Icon, File01Icon, Flag02Icon, SentIcon } from "@hugeicons/core-free-icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { t } from "@/i18n/strings";

// Dev-only preview of every base component variant (/dev/styleguide). Copy here is not user-facing.

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-muted">{title}</h2>
      {children}
    </section>
  );
}

export function StyleguideScreen() {
  const [selectedCard, setSelectedCard] = useState(true);
  const [chip, setChip] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <main className="mx-auto max-w-md space-y-8 px-4 py-6">
      <h1 className="text-2xl font-semibold">{t("dev.styleguide.title")}</h1>

      <Section title="Button">
        <Button variant="primary" fullWidth icon={SentIcon}>
          Primary
        </Button>
        <Button variant="primary" fullWidth disabled>
          Primary (disabled)
        </Button>
        <div className="flex gap-2">
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
        </div>
        <div className="flex gap-1">
          <Button variant="icon" icon={File01Icon} label={t("action.source")} />
          <Button variant="icon" icon={Book02Icon} label={t("action.guideline")} />
          <Button variant="icon" icon={Download04Icon} label={t("action.export")} />
          <Button variant="icon" icon={Flag02Icon} label={t("action.flag")} tone="flag" />
        </div>
      </Section>

      <Section title="Badge">
        <div className="flex flex-wrap gap-2">
          <Badge variant="verified" />
          <Badge variant="ai_inferred" />
          <Badge variant="not_documented" />
          <Badge variant="contradiction" />
          <Badge variant="neutral">Neutral</Badge>
        </div>
      </Section>

      <Section title="Card">
        <Card>Default</Card>
        <Card tone="verified">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-xs text-ink-muted">Antikoagulation</p>
              <p className="font-semibold">Apixaban 5 mg 1-0-1</p>
            </div>
            <Badge variant="verified" />
          </div>
        </Card>
        <Card tone="inferred">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-xs text-ink-muted">Atemweg</p>
              <p className="font-semibold">Schwierige Intubation möglich</p>
            </div>
            <Badge variant="ai_inferred" />
          </div>
        </Card>
        <Card tone="undocumented">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-xs text-ink-muted">PONV-Anamnese</p>
              <p className="text-undocumented">{t("trust.not_documented")}</p>
            </div>
            <Badge variant="not_documented" />
          </div>
        </Card>
        <Card tone="contradiction">
          <Badge variant="contradiction" />
          <p className="mt-2 font-semibold">Allergien</p>
        </Card>
        <Card selectable selected={selectedCard} onClick={() => setSelectedCard((s) => !s)}>
          Selectable ({selectedCard ? "selected" : "not selected"})
        </Card>
      </Section>

      <Section title="Chip">
        <div className="flex flex-wrap gap-2">
          {["Chip A", "Chip B", "Chip C"].map((label, i) => (
            <Chip key={label} selected={chip === i} onClick={() => setChip(i)}>
              {label}
            </Chip>
          ))}
        </div>
      </Section>

      <Section title="Modal">
        <Button variant="secondary" onClick={() => setModalOpen(true)}>
          Open modal
        </Button>
        <Modal
          open={modalOpen}
          onOpenChange={setModalOpen}
          title="Entlassbrief Innere Medizin, Juni 2015"
          description="Quelle"
          footer={
            <Button variant="primary" fullWidth onClick={() => setModalOpen(false)}>
              {t("action.close")}
            </Button>
          }
        >
          <p className="rounded-lg bg-canvas p-3 text-sm leading-relaxed">
            … <mark className="rounded-sm bg-inferred-soft px-0.5">Bekannte Allergie: Penicillin (Exanthem 2009).</mark> …
          </p>
        </Modal>
      </Section>
    </main>
  );
}
