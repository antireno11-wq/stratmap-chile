import { cn } from "@/lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "secondary" | "success" | "warning" | "danger" | "outline";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold border",
        {
          "bg-blue-100 text-blue-800 border-blue-200": variant === "default",
          "bg-slate-100 text-slate-700 border-slate-200": variant === "secondary",
          "bg-emerald-100 text-emerald-800 border-emerald-200": variant === "success",
          "bg-amber-100 text-amber-800 border-amber-200": variant === "warning",
          "bg-red-100 text-red-800 border-red-200": variant === "danger",
          "bg-white text-slate-700 border-slate-300": variant === "outline",
        },
        className
      )}
      {...props}
    />
  );
}
