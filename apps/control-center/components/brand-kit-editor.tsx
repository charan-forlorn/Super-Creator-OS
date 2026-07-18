"use client";

import { useState } from "react";
import { useBrandKit, type BrandKitInput } from "@/lib/brand-kit-client";

const EMPTY: BrandKitInput = {
  name: "",
  colors: { primary: "", secondary: "", accent: "", neutrals: [] },
  fonts: { heading: "", body: "" },
  logo: { asset_ref: "", kind: "local-ref" },
  contact: { name: "", email: "", socials: [] },
  basic_cta: { label: "", target: "" },
};

export function BrandKitEditor() {
  const bk = useBrandKit();
  const [form, setForm] = useState<BrandKitInput>(EMPTY);
  const [clientErrors, setClientErrors] = useState<string[]>([]);
  const [transitionErrors, setTransitionErrors] = useState<string[]>([]);

  function update<K extends keyof BrandKitInput>(key: K, value: BrandKitInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function onSave() {
    setTransitionErrors([]);
    const res = await bk.save(form);
    if (!res.ok || !res.record) {
      setTransitionErrors([res.error_code ?? "SAVE_FAILED", res.detail ?? ""].filter(Boolean));
      return;
    }
    setClientErrors([]);
    setTransitionErrors([]);
    setForm(EMPTY);
  }

  return (
    <section
      className="rounded-card border border-border bg-surface p-4"
      aria-labelledby="brand-kit-title"
      aria-label="Brand kit editor"
    >
      <h3 id="brand-kit-title" className="text-sm font-semibold text-ink">
        Brand Kit (local only)
      </h3>
      <p className="mt-1 max-w-2xl text-xs text-ink-muted">
        Store brand colors, fonts, logo reference, contact info, and a basic CTA. All data is
        persisted in an authoritative local store (memory/runtime/control-center/brand-kit-v1.json).
        No external network; the logo is a server-resolved local reference.
      </p>

      {bk.loadState === "loading" ? (
        <p className="mt-4 text-xs text-ink-faint" role="status">
          Reading authoritative local SCOS state…
        </p>
      ) : null}

      {bk.truthStatus === "UNAVAILABLE" ? (
        <p className="mt-4 rounded-lg border border-status-failed/40 bg-status-failed/10 p-3 text-xs text-status-failed" role="alert">
          Authoritative store unavailable — saving disabled.
        </p>
      ) : null}

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Kit name</span>
          <input
            aria-label="Brand kit name"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Logo local reference</span>
          <input
            aria-label="Logo local reference"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={form.logo.asset_ref}
            onChange={(e) => update("logo", { asset_ref: e.target.value, kind: "local-ref" })}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Primary color</span>
          <input
            aria-label="Primary color"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={form.colors.primary}
            onChange={(e) => update("colors", { ...form.colors, primary: e.target.value })}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Secondary color</span>
          <input
            aria-label="Secondary color"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={form.colors.secondary}
            onChange={(e) => update("colors", { ...form.colors, secondary: e.target.value })}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Accent color</span>
          <input
            aria-label="Accent color"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={form.colors.accent}
            onChange={(e) => update("colors", { ...form.colors, accent: e.target.value })}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Heading font</span>
          <input
            aria-label="Heading font"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={form.fonts.heading}
            onChange={(e) => update("fonts", { ...form.fonts, heading: e.target.value })}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Body font</span>
          <input
            aria-label="Body font"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={form.fonts.body}
            onChange={(e) => update("fonts", { ...form.fonts, body: e.target.value })}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Contact name</span>
          <input
            aria-label="Contact name"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={form.contact.name}
            onChange={(e) => update("contact", { ...form.contact, name: e.target.value })}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Contact email</span>
          <input
            aria-label="Contact email"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={form.contact.email}
            onChange={(e) => update("contact", { ...form.contact, email: e.target.value })}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">CTA label</span>
          <input
            aria-label="CTA label"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={form.basic_cta.label}
            onChange={(e) => update("basic_cta", { ...form.basic_cta, label: e.target.value })}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">CTA target</span>
          <input
            aria-label="CTA target"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={form.basic_cta.target}
            onChange={(e) => update("basic_cta", { ...form.basic_cta, target: e.target.value })}
          />
        </label>
      </div>

      {clientErrors.length ? (
        <p className="mt-3 text-xs text-status-failed" role="alert">
          {clientErrors.join(", ")}
        </p>
      ) : null}
      {transitionErrors.length ? (
        <p className="mt-3 text-xs text-status-failed" role="alert">
          {transitionErrors.join(" · ")}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-lg border border-border-soft bg-surface-2 px-4 py-2 text-sm font-semibold text-ink"
          disabled={bk.truthStatus !== "AVAILABLE_WITH_DATA" && bk.truthStatus !== "EMPTY"}
          onClick={onSave}
        >
          Save brand kit
        </button>
        <button
          type="button"
          className="rounded-lg border border-border-soft bg-surface-2 px-4 py-2 text-sm font-semibold text-ink"
          onClick={() => bk.refresh()}
        >
          Refresh authoritative state
        </button>
      </div>

      {bk.records.length ? (
        <ul className="mt-4 grid gap-2" aria-label="Saved brand kits">
          {bk.records.map((kit) => (
            <li key={kit.brand_kit_id} className="rounded-lg border border-border-soft bg-surface-2 p-3 text-xs text-ink-muted">
              <span className="font-semibold text-ink">{kit.name}</span> · {kit.brand_kit_id} · {kit.colors.primary} / {kit.colors.secondary} / {kit.colors.accent}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
