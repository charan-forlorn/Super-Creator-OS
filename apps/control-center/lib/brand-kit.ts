/**
 * Phase 2 — Brand Kit type definitions (local-only, server-resolved).
 *
 * A Brand Kit is a reference-only resource for a project draft. The browser
 * never supplies a filesystem path or URL for the logo; the logo is stored as
 * a server-resolved local asset reference. The brand kit is resolved
 * server-side and never fetched by the browser from an arbitrary location.
 */

export const BRAND_KIT_SCHEMA_VERSION = 1;
export const BRAND_KIT_STORE_KIND = "scos.brand_kit.v1";

export interface BrandKitColors {
  primary: string;
  secondary: string;
  accent: string;
  neutrals: string[];
}

export interface BrandKitFonts {
  heading: string;
  body: string;
}

export interface BrandKitLogo {
  /** Server-resolved local asset reference (never a browser-supplied path/URL). */
  asset_ref: string;
  kind: "local-ref";
}

export interface BrandKitContact {
  name: string;
  email: string;
  socials: { label: string; handle: string }[];
}

export interface BrandKitCta {
  label: string;
  /** Validated, never auto-fetched/embedded. Kept separate from the remote-asset guard. */
  target: string;
}

export interface BrandKit {
  brand_kit_id: string;
  schema_version: number;
  name: string;
  colors: BrandKitColors;
  fonts: BrandKitFonts;
  logo: BrandKitLogo;
  contact: BrandKitContact;
  basic_cta: BrandKitCta;
}
