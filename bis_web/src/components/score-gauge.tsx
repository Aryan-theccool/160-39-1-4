"use client";

import { cn } from "@/lib/utils";

/**
 * A semicircular compliance gauge.
 *
 * A gauge is honest here, unlike on the search cards: `compliance_score` really
 * is a 0..1 ratio defined by a stated formula, so a needle at 0.77 means
 * something. The band labels are the API's own grade names.
 */
export function ScoreGauge({
  score,
  label,
  color = "#FF9933",
  sublabel,
  className,
}: {
  score: number;
  label?: string;
  color?: string;
  sublabel?: string;
  className?: string;
}) {
  const clamped = Math.min(1, Math.max(0, score));
  const radius = 80;
  const cx = 100;
  const cy = 100;
  // Half circle, so the arc spans 180 degrees from left to right.
  const circumference = Math.PI * radius;
  const filled = circumference * clamped;

  return (
    <div className={cn("flex flex-col items-center", className)}>
      <svg viewBox="0 0 200 118" className="h-[130px] w-[220px]" role="img"
        aria-label={`Compliance score ${Math.round(clamped * 100)} out of 100`}>
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          stroke="hsl(var(--muted))"
          strokeWidth={16}
          strokeLinecap="round"
        />
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          stroke={color}
          strokeWidth={16}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference}`}
          className="transition-all duration-700 ease-out"
        />
        <text
          x={cx}
          y={cy - 18}
          textAnchor="middle"
          className="fill-foreground text-[34px] font-bold"
        >
          {Math.round(clamped * 100)}
        </text>
        <text
          x={cx}
          y={cy - 2}
          textAnchor="middle"
          className="fill-muted-foreground text-[11px]"
        >
          out of 100
        </text>
      </svg>
      {label ? (
        <p className="text-center text-sm font-semibold tracking-tight">{label}</p>
      ) : null}
      {sublabel ? (
        <p className="text-center text-xs text-muted-foreground">{sublabel}</p>
      ) : null}
    </div>
  );
}
