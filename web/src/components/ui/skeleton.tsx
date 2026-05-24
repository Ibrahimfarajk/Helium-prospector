import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-[pulse-subtle_2s_ease-in-out_infinite] rounded-md bg-[var(--muted)]", className)}
      {...props}
    />
  );
}

export { Skeleton };
