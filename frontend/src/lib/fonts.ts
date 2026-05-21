/**
 * User-font loading for the canvas editor.
 *
 * Uploaded fonts are registered as FontFaces on `document.fonts` so both the
 * Fabric canvas and regular CSS can render them by family name. Loading is
 * idempotent — each family is fetched at most once per page.
 */

import { api, resolveImageUrl } from "./api";

export interface UserFont {
  family: string;
  filename: string;
  url: string;
}

const loaded = new Set<string>();

/** Register one user font as a FontFace. Resolves once it's usable (or on failure). */
export async function loadUserFont(family: string, url: string): Promise<void> {
  if (loaded.has(family)) return;
  loaded.add(family);
  try {
    const face = new FontFace(family, `url(${resolveImageUrl(url)})`);
    await face.load();
    document.fonts.add(face);
  } catch (e) {
    // Drop the marker so a later attempt (e.g. re-upload) can retry.
    loaded.delete(family);
    console.warn(`[fonts] failed to load "${family}"`, e);
  }
}

/** Fetch the user's uploaded fonts and register every one. Returns the list. */
export async function loadAllUserFonts(): Promise<UserFont[]> {
  try {
    const { fonts } = await api.getFonts();
    await Promise.all(fonts.map((f) => loadUserFont(f.family, f.url)));
    return fonts;
  } catch {
    return [];
  }
}
