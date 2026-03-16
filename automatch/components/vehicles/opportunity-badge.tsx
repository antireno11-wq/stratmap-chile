import type { OpportunityScore } from "@prisma/client";
import { cn, OPPORTUNITY_LABELS, OPPORTUNITY_COLORS } from "@/lib/utils";

interface OpportunityBadgeProps {
  score: OpportunityScore;
  className?: string;
  size?: "sm" | "md" | "lg";
}

export function OpportunityBadge({ score, className, size = "md" }: OpportunityBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 font-semibold rounded-full border",
        OPPORTUNITY_COLORS[score],
        {
          "text-xs px-2 py-0.5": size === "sm",
          "text-xs px-2.5 py-1": size === "md",
          "text-sm px-3 py-1.5": size === "lg",
        },
        className
      )}
    >
      {score === "VERY_GOOD_DEAL" && <span>🔥</span>}
      {score === "GOOD_DEAL" && <span>✅</span>}
      {score === "FAIR_PRICE" && <span>➡️</span>}
      {score === "OVERPRICED" && <span>⚠️</span>}
      {OPPORTUNITY_LABELS[score]}
    </span>
  );
}
