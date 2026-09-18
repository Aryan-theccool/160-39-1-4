import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/** One page title block, so every page starts the same way. */
export function PageHeader({
  title,
  description,
  icon: Icon,
  children,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  icon?: LucideIcon;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-6 flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="space-y-1">
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight sm:text-3xl">
          {Icon ? <Icon className="h-6 w-6 text-tricolor-saffron" /> : null}
          {title}
        </h1>
        {description ? (
          <p className="max-w-3xl text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {children}
    </div>
  );
}
