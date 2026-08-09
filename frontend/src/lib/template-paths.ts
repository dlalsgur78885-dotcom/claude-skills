/** Helpers for navigating the template JSON tree by dotted/bracketed path strings.
 *
 * Path examples:
 *   layouts.grid_2x2.decorations[0]
 *   layouts.grid_2x2.text_slots[1].position
 *   layouts.grid_2x2.grid.item_box.title_style
 */

export type TemplateValue = unknown;

function tokenize(path: string): (string | number)[] {
  const tokens: (string | number)[] = [];
  for (const part of path.split(".")) {
    let buf = "";
    for (const ch of part) {
      if (ch === "[") {
        if (buf) tokens.push(buf);
        buf = "";
      } else if (ch === "]") {
        if (buf) tokens.push(Number(buf));
        buf = "";
      } else {
        buf += ch;
      }
    }
    if (buf) tokens.push(buf);
  }
  return tokens;
}

export function getByPath(root: unknown, path: string): TemplateValue {
  let cur: unknown = root;
  for (const t of tokenize(path)) {
    if (cur == null) return undefined;
    cur = (cur as Record<string | number, unknown>)[t];
  }
  return cur;
}

/** Returns a deep-cloned root with the value at `path` replaced. */
export function setByPath(root: unknown, path: string, value: unknown): unknown {
  const tokens = tokenize(path);
  const cloned: unknown = JSON.parse(JSON.stringify(root));
  let cur: Record<string | number, unknown> = cloned as Record<string | number, unknown>;
  for (let i = 0; i < tokens.length - 1; i++) {
    const t = tokens[i];
    if (cur[t] == null) {
      const next = tokens[i + 1];
      cur[t] = typeof next === "number" ? [] : {};
    }
    cur = cur[t] as Record<string | number, unknown>;
  }
  cur[tokens[tokens.length - 1]] = value;
  return cloned;
}

/** Returns a deep-cloned root with the array element at `arrayPath[idx]` removed.
 *  No-op when path doesn't resolve to an array.
 */
export function removeArrayItem(root: unknown, path: string): unknown {
  const tokens = tokenize(path);
  if (tokens.length === 0) return root;
  const lastIdx = tokens[tokens.length - 1];
  if (typeof lastIdx !== "number") return root;

  const cloned: unknown = JSON.parse(JSON.stringify(root));
  let cur: Record<string | number, unknown> = cloned as Record<string | number, unknown>;
  for (let i = 0; i < tokens.length - 1; i++) {
    cur = cur[tokens[i]] as Record<string | number, unknown>;
    if (cur == null) return root;
  }
  if (Array.isArray(cur)) cur.splice(lastIdx, 1);
  return cloned;
}
