import { cn } from "@/lib/utils";

/**
 * One empty state for the whole app, so "nothing here" always looks the same
 * and never looks like a bug. `hint` is where the fix or the next step goes.
 */
export function EmptyState({
  icon: Icon,
  title,
  hint,
  action,
  className,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  hint?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/30 px-6 py-14 text-center",
        className,
      )}
    >
      {Icon ? <Icon className="h-8 w-8 text-muted-foreground/70" /> : null}
      <p className="font-medium">{title}</p>
      {hint ? <div className="max-w-md text-sm text-muted-foreground">{hint}</div> : null}
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  );
}
