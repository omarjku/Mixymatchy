import { AnimatePresence, motion } from "motion/react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft01Icon, HelpCircleIcon, MoreVerticalIcon } from "@hugeicons/core-free-icons";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/primitives/dropdown-menu";
import { Button } from "@/components/ui/Button";
import { Icon, type IconGlyph } from "@/components/ui/Icon";
import { t } from "@/i18n/strings";
import { cn } from "@/lib/utils";

// Top bar for every screen: solid brand periwinkle (#4a5bef, white text 5.2:1), SE logo + name as the
// home link, optional back button, an optional title that replaces the name (e.g. the patient once the
// patient card has scrolled away), always-visible actions, and secondary actions that sit inline from
// tablet width and move into a "⋯" menu on phones. Help is always available.

export interface AppBarAction {
  id: string;
  label: string;
  icon: IconGlyph;
  onClick: () => void;
  emphasis?: boolean; // shown as a white pill with its label from tablet width (e.g. "Neue Anfrage")
  text?: string; // short visible text instead of an icon from tablet width (e.g. "DE")
}

export interface AppBarProps {
  back?: { label: string; onClick: () => void };
  title?: React.ReactNode;
  showTitle?: boolean;
  actions?: React.ReactNode; // always visible, e.g. the read-aloud button
  menuActions?: AppBarAction[];
  contentClassName?: string; // match the page's max width so bar content lines up with the page
}

export function AppBar({ back, title, showTitle = false, actions, menuActions = [], contentClassName }: AppBarProps) {
  const navigate = useNavigate();
  const help: AppBarAction = {
    id: "help",
    label: t("appbar.help"),
    icon: HelpCircleIcon,
    onClick: () => navigate("/hilfe"),
  };
  const titleVisible = showTitle && Boolean(title);

  return (
    <header className="sticky top-0 z-20 bg-primary-strong pt-[env(safe-area-inset-top)] text-primary-ink shadow-[0_1px_0_rgba(20,24,49,0.08),0_6px_16px_-10px_rgba(47,59,176,0.6)]">
      <div className={cn("mx-auto flex h-14 max-w-md items-center gap-1 px-2 md:px-6", contentClassName)}>
        {back && (
          <Button variant="icon" tone="onBrand" icon={ArrowLeft01Icon} label={back.label} onClick={back.onClick} />
        )}

        <Link
          to="/"
          aria-label={t("appbar.home")}
          className="flex shrink-0 items-center gap-2 rounded-xl p-1 outline-hidden focus-visible:ring-2 focus-visible:ring-white"
        >
          <img src="/logo-128.png" alt="" width={32} height={32} className="size-8 rounded-lg" />
          {!titleVisible && <span className="text-[17px] font-semibold tracking-tight">{t("app.name")}</span>}
        </Link>

        <div className="relative ml-1 min-w-0 flex-1 overflow-hidden">
          <AnimatePresence mode="popLayout" initial={false}>
            {titleVisible && (
              <motion.div
                key="title"
                initial={{ y: 16, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={{ y: 16, opacity: 0 }}
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
                className="min-w-0"
              >
                {title}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {actions}

        {/* Tablet and desktop: everything inline */}
        <div className="hidden items-center gap-1 md:flex">
          {[...menuActions, help].map((a) =>
            a.emphasis ? (
              <button
                key={a.id}
                type="button"
                onClick={a.onClick}
                className="ml-1 inline-flex h-9 items-center gap-1.5 rounded-full bg-surface px-3.5 text-sm font-semibold text-primary-deep transition-colors hover:bg-primary-soft focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-primary-strong"
              >
                <Icon icon={a.icon} size={16} />
                {a.label}
              </button>
            ) : a.text ? (
              <button
                key={a.id}
                type="button"
                onClick={a.onClick}
                aria-label={a.label}
                title={a.label}
                className="h-9 rounded-full border border-white/40 px-3 text-xs font-semibold transition-colors hover:bg-white/15 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-white"
              >
                {a.text}
              </button>
            ) : (
              <Button key={a.id} variant="icon" tone="onBrand" icon={a.icon} label={a.label} onClick={a.onClick} />
            ),
          )}
        </div>

        {/* Phone: short text actions (the EN/DE toggle) stay visible; the rest + help go into a menu */}
        {menuActions
          .filter((a) => a.text)
          .map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={a.onClick}
              aria-label={a.label}
              title={a.label}
              className="h-9 rounded-full border border-white/40 px-3 text-xs font-semibold transition-colors hover:bg-white/15 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-white md:hidden"
            >
              {a.text}
            </button>
          ))}
        <div className="md:hidden">
          {menuActions.filter((a) => !a.text).length === 0 ? (
            <Button variant="icon" tone="onBrand" icon={help.icon} label={help.label} onClick={help.onClick} />
          ) : (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="icon" tone="onBrand" icon={MoreVerticalIcon} label={t("appbar.menu")} />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={6} className="min-w-52 rounded-xl border-line p-1.5">
                {[...menuActions.filter((a) => !a.text), help].map((a) => (
                  <DropdownMenuItem
                    key={a.id}
                    onSelect={a.onClick}
                    className="min-h-11 gap-3 rounded-lg px-3 text-[15px] text-ink focus:bg-primary-soft focus:text-primary-deep"
                  >
                    <Icon icon={a.icon} size={18} className="text-primary-deep" />
                    {a.label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </header>
  );
}
