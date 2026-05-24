import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--ring)] focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-[var(--secondary)] text-[var(--secondary-foreground)]",
        outline: "border-[var(--border)] text-[var(--foreground)]",
        // Tier-Variants
        t1: "border-transparent bg-[oklch(0.65_0.23_27_/_0.15)] text-[oklch(0.78_0.18_27)]",
        t2: "border-transparent bg-[oklch(0.71_0.19_56_/_0.15)] text-[oklch(0.82_0.16_56)]",
        t3: "border-transparent bg-[oklch(0.78_0.15_86_/_0.12)] text-[oklch(0.85_0.13_86)]",
        // Status-Variants
        "status-new": "border-[var(--border)] text-[var(--muted-foreground)]",
        "status-contacted":
          "border-transparent bg-[oklch(0.62_0.2_252_/_0.15)] text-[oklch(0.74_0.18_252)]",
        "status-meeting":
          "border-transparent bg-[oklch(0.6_0.22_295_/_0.15)] text-[oklch(0.74_0.2_295)]",
        "status-won":
          "border-transparent bg-[oklch(0.7_0.17_152_/_0.15)] text-[oklch(0.82_0.16_152)]",
        "status-lost": "border-[var(--border)] text-[var(--muted-foreground)] opacity-60",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
