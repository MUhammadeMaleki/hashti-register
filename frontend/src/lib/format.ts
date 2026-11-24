export function formatToman(amount: number): string {
  return `${new Intl.NumberFormat("fa-IR").format(amount)} تومان`;
}

export function persianDigits(value: string): string {
  return value.replace(/[0-9]/g, (digit) => String.fromCharCode(1776 + Number(digit)));
}

export function formatJalali(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
    year: "numeric", month: "long", day: "numeric",
  }).format(date);
}

export function normalizeMobile(value: string): string {
  const digits = value.replace(/[۰-۹]/g, (digit) => String(digit.charCodeAt(0) - 1776))
    .replace(/[٠-٩]/g, (digit) => String(digit.charCodeAt(0) - 1632))
    .replace(/[\s-]/g, "");
  if (digits.startsWith("+98")) return `0${digits.slice(3)}`;
  if (digits.startsWith("98") && digits.length === 12) return `0${digits.slice(2)}`;
  return digits;
}

export function latinDigits(value: string): string {
  return value.replace(/[۰-۹]/g, (digit) => String(digit.charCodeAt(0) - 1776))
    .replace(/[٠-٩]/g, (digit) => String(digit.charCodeAt(0) - 1632));
}

const jalaliParts = new Intl.DateTimeFormat("en-US-u-ca-persian", {
  timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit",
});

function persianTuple(date: Date): [number, number, number] {
  const parts = jalaliParts.formatToParts(date);
  const read = (kind: string) => Number(parts.find((part) => part.type === kind)?.value);
  return [read("year"), read("month"), read("day")];
}

export function isoToJalali(iso: string): string {
  const [year, month, day] = persianTuple(new Date(`${iso}T12:00:00Z`));
  return `${year}/${String(month).padStart(2, "0")}/${String(day).padStart(2, "0")}`;
}

export function jalaliToIso(input: string): string | null {
  const match = /^(\d{4})\/(\d{1,2})\/(\d{1,2})$/.exec(latinDigits(input.trim()));
  if (!match) return null;
  const target: [number, number, number] = [Number(match[1]), Number(match[2]), Number(match[3])];
  if (target[0] < 1300 || target[0] > 1500 || target[1] < 1 || target[1] > 12 ||
      target[2] < 1 || target[2] > 31) return null;
  const dayMs = 86_400_000;
  let low = Math.floor(Date.UTC(1900, 0, 1) / dayMs);
  let high = Math.floor(Date.UTC(2200, 0, 1) / dayMs);
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const current = persianTuple(new Date(mid * dayMs));
    const comparison = current[0] - target[0] || current[1] - target[1] ||
      current[2] - target[2];
    if (comparison === 0) return new Date(mid * dayMs).toISOString().slice(0, 10);
    if (comparison < 0) low = mid + 1;
    else high = mid - 1;
  }
  return null;
}
