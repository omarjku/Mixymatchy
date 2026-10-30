import { MinusSignIcon, PlusSignIcon } from "@hugeicons/core-free-icons";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/primitives/accordion";
import { Icon } from "@/components/ui/Icon";

// Question list, built from Watermelon UI's faq-1 (registry.watermelon.sh/r/faq-1.json) on the shadcn
// accordion: one answer open at a time, plus/minus toggle. Without faq-1's badge-above-headline and
// marketing-size title; icons are Hugeicons instead of react-icons.

export interface FaqItem {
  id: string;
  question: string;
  answer: string;
}

export function Faq({ items }: { items: FaqItem[] }) {
  return (
    <Accordion type="single" collapsible className="flex flex-col gap-2">
      {items.map((item) => (
        <AccordionItem
          key={item.id}
          value={item.id}
          className="rounded-lg border border-line bg-surface px-4 last:border-b"
        >
          <AccordionTrigger className="group items-center gap-3 py-4 text-left hover:no-underline focus-visible:ring-primary [&>svg]:hidden">
            <span className="flex-1 text-[15px] font-medium leading-snug text-ink md:text-base">{item.question}</span>
            <span
              aria-hidden
              className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary-deep group-data-[state=open]:bg-primary-strong group-data-[state=open]:text-primary-ink"
            >
              <Icon icon={PlusSignIcon} size={16} className="group-data-[state=open]:hidden" />
              <Icon icon={MinusSignIcon} size={16} className="hidden group-data-[state=open]:block" />
            </span>
          </AccordionTrigger>
          <AccordionContent className="pb-4 pr-11 text-[15px] leading-relaxed text-ink-muted">
            {item.answer}
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}
