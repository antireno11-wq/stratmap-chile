import { cn } from "@/lib/utils";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "outline";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

export function Button({
  className,
  variant = "primary",
  size = "md",
  loading,
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center font-medium rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none",
        {
          "bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800": variant === "primary",
          "bg-slate-100 text-slate-700 hover:bg-slate-200 active:bg-slate-300": variant === "secondary",
          "text-slate-600 hover:bg-slate-100 active:bg-slate-200": variant === "ghost",
          "bg-red-600 text-white hover:bg-red-700": variant === "danger",
          "border border-slate-300 text-slate-700 bg-white hover:bg-slate-50": variant === "outline",
        },
        {
          "text-xs px-3 py-1.5 gap-1.5": size === "sm",
          "text-sm px-4 py-2 gap-2": size === "md",
          "text-base px-6 py-3 gap-2": size === "lg",
        },
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <svg className="animate-spin h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      )}
      {children}
    </button>
  );
}
