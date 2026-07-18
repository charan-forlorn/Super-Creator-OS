import type { ReactNode } from "react";

export function WizardStep({
  id,
  title,
  children,
}: Readonly<{ id: string; title: string; children: ReactNode }>) {
  return (
    <section className="rounded-card border border-border bg-surface p-4" aria-labelledby={id}>
      <h3 id={id} className="text-sm font-semibold text-ink">
        {title}
      </h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function FieldLabel({ htmlFor, text }: Readonly<{ htmlFor: string; text: string }>) {
  return <span className="mb-1 block text-xs font-semibold text-ink">{text}</span>;
}
