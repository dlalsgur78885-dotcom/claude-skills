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

// family → its in-flight/finished load, so a second caller waits for the same
// load instead of drawing with the fallback face while the first is fetching.
const loaded = new Map<string, Promise<void>>();

/** Register one user font as a FontFace. Resolves once it's usable (or on failure). */
export function loadUserFont(family: string, url: string): Promise<void> {
  const pending = loaded.get(family);
  if (pending) return pending;
  const load = (async () => {
    try {
      // Quoted — an unquoted url() fails to parse when the filename has spaces.
      const face = new FontFace(family, `url("${resolveImageUrl(url)}")`);
      await face.load();
      document.fonts.add(face);
    } catch (e) {
      // Drop the marker so a later attempt (e.g. re-upload) can retry.
      loaded.delete(family);
      console.warn(`[fonts] failed to load "${family}"`, e);
    }
  })();
  loaded.set(family, load);
  return load;
}

// The font list, fetched once per page — the template previews re-render on
// every keystroke, so they must not hit /fonts each time.
let fontListPromise: Promise<UserFont[]> | null = null;

/** The user's uploaded fonts, without registering them. Cached per page. */
export function listUserFonts(): Promise<UserFont[]> {
  if (!fontListPromise) {
    fontListPromise = api.getFonts().then((r) => r.fonts).catch(() => {
      fontListPromise = null; // retry on the next call
      return [];
    });
  }
  return fontListPromise;
}

/** Upload a font file, register it, and add it to the cached list. */
export async function uploadUserFont(file: File): Promise<UserFont> {
  const f = await api.uploadFont(file);
  await loadUserFont(f.family, f.url);
  const fonts = await listUserFonts();
  fontListPromise = Promise.resolve([...fonts.filter((p) => p.filename !== f.filename), f]);
  return f;
}

/** Delete an uploaded font and drop it from the cached list. */
export async function deleteUserFont(font: UserFont): Promise<UserFont[]> {
  await api.deleteFont(font.filename);
  loaded.delete(font.family); // a re-upload under the same name must load again
  const fonts = (await listUserFonts()).filter((p) => p.filename !== font.filename);
  fontListPromise = Promise.resolve(fonts);
  return fonts;
}

/** Register just the uploaded fonts among `families`, so a template preview
 *  doesn't download every font the user owns. Unknown names are ignored. */
export async function ensureUserFonts(families: (string | undefined | null)[]): Promise<void> {
  const fonts = await listUserFonts();
  await Promise.all(
    fonts.filter((f) => families.includes(f.family)).map((f) => loadUserFont(f.family, f.url)),
  );
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
