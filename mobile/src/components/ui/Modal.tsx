import * as React from "react";
import { Cancel01Icon } from "@hugeicons/core-free-icons";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/primitives/drawer";
import { Icon } from "@/components/ui/Icon";
import { t } from "@/i18n/strings";
import { cn } from "@/lib/utils";

// Bottom-sheet modal (swipe down, backdrop tap or close button to dismiss).
// Base for SourceModal and FlagModal.

export interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  footer?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}

export function Modal({ open, onOpenChange, title, description, footer, children, className }: ModalProps) {
  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent
        className={cn(
          "mx-auto max-h-[88dvh] w-full max-w-md rounded-t-3xl border-line pb-[env(safe-area-inset-bottom)]",
          className,
        )}
      >
        <DrawerHeader className="relative px-5 pb-2 pt-3 text-left">
          <DrawerTitle className="pr-10 text-[17px] font-semibold leading-snug text-ink">{title}</DrawerTitle>
          {description && <DrawerDescription className="text-ink-muted">{description}</DrawerDescription>}
          <DrawerClose
            aria-label={t("action.close")}
            className="absolute right-3 top-1 flex h-11 w-11 items-center justify-center rounded-full text-ink-muted hover:bg-primary-soft hover:text-primary-deep"
          >
            <Icon icon={Cancel01Icon} size={20} />
          </DrawerClose>
        </DrawerHeader>
        <div className="overflow-y-auto px-5 pb-4">{children}</div>
        {footer && <DrawerFooter className="border-t border-line px-5 pt-3">{footer}</DrawerFooter>}
      </DrawerContent>
    </Drawer>
  );
}
