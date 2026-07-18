import { BrandKitEditor } from "@/components/brand-kit-editor";

export default function BrandKitPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-lg font-semibold text-ink">Brand Kit</h1>
        <p className="mt-1 text-xs text-ink-muted">
          Local-only brand configuration for the Solo Operator MVP.
        </p>
      </header>
      <BrandKitEditor />
    </main>
  );
}
