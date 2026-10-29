/**
 * USD amounts travel as decimal strings with up to 6 fractional digits
 * (backend `format_usd`). All arithmetic is done in integer micro-USD so the
 * frontend never approves an amount that drifted through floating point.
 */

const AMOUNT = /^(\d+)(?:\.(\d{1,6}))?$/;
const MICROS_PER_USD = 1_000_000n;

/** Parse a wire USD string into integer micro-USD. Throws on malformed input. */
export function toMicros(amount: string): bigint {
  const m = AMOUNT.exec(amount.trim());
  if (!m) throw new Error(`Invalid USD amount: ${amount}`);
  const [, whole, frac = ""] = m;
  return BigInt(whole) * MICROS_PER_USD + BigInt(frac.padEnd(6, "0"));
}

/** Format micro-USD as a wire string with 2–6 fractional digits (e.g. "0.50", "0.123456"). */
export function fromMicros(micros: bigint): string {
  const whole = micros / MICROS_PER_USD;
  const frac = (micros % MICROS_PER_USD).toString().padStart(6, "0").replace(/0{1,4}$/, "");
  return `${whole}.${frac.padEnd(2, "0")}`;
}

/** Exact sum of wire USD strings, returned as a wire string. */
export function sumUsd(amounts: Iterable<string>): string {
  let total = 0n;
  for (const a of amounts) total += toMicros(a);
  return fromMicros(total);
}

/**
 * Display form of a wire USD string in the UI `locale`, e.g. "1.250000" ->
 * "$1.25" (en) or "1,25 $" (de). Intl lays out the symbol and separators
 * around the bigint whole part; the fraction digits are spliced in verbatim,
 * so no amount passes through a float.
 */
export function formatUsd(amount: string, locale: string): string {
  const [whole, frac] = fromMicros(toMicros(amount)).split(".");
  const digits = frac.length;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
    .formatToParts(BigInt(whole))
    .map((p) => (p.type === "fraction" ? frac : p.value))
    .join("");
}
