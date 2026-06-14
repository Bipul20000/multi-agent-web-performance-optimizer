import React from "react";
import { cn } from "@/lib/utils";

export function ScoreCircle({ score, label, className }: { score: number, label: string, className?: string }) {
  let colorClass = "text-red-400 border-red-400";
  if (score >= 90) {
    colorClass = "text-emerald-400 border-emerald-400";
  } else if (score >= 50) {
    colorClass = "text-amber-400 border-amber-400";
  }

  return (
    <div className={cn("flex flex-col items-center justify-center gap-2", className)}>
      <div className={cn("flex items-center justify-center rounded-full border-2 w-12 h-12 text-sm font-bold", colorClass)}>
        {Math.round(score)}
      </div>
      <span className="text-[10px] uppercase tracking-wider text-slate-400 whitespace-nowrap">{label}</span>
    </div>
  );
}

export function ScoreGroup({ scores, className }: { scores: { performance?: number, accessibility?: number, best_practices?: number, seo?: number }, className?: string }) {
  if (!scores) return null;
  return (
    <div className={cn("flex items-center gap-4", className)}>
      <ScoreCircle score={scores.performance || 0} label="Performance" />
      <ScoreCircle score={scores.accessibility || 0} label="Accessibility" />
      <ScoreCircle score={scores.best_practices || 0} label="Best Practices" />
      <ScoreCircle score={scores.seo || 0} label="SEO" />
    </div>
  );
}
