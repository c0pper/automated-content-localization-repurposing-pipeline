/** WCAG 2.x contrast-ratio helpers for validating theme color pairings. */

/** Parse `#rgb` or `#rrggbb` into [r, g, b] in 0..255. */
export function hexToRgb(hex: string): [number, number, number] {
  let h = hex.trim().replace(/^#/, "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  if (!/^[0-9a-f]{6}$/i.test(h)) throw new Error(`Invalid hex color: ${hex}`);
  const n = parseInt(h, 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

/** Relative luminance per WCAG 2.x. */
export function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** Contrast ratio between two colors (1..21), order-independent. */
export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** WCAG AA: 4.5:1 for normal text, 3:1 for large text / UI components. */
export function meetsWcagAA(fg: string, bg: string, opts: { largeText?: boolean } = {}): boolean {
  return contrastRatio(fg, bg) >= (opts.largeText ? 3 : 4.5);
}
