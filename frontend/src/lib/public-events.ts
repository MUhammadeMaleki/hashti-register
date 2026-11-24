import { formatJalali, formatToman, persianDigits } from "@/lib/format";

export type PublicEvent = {
  id: number; event_number: number; title: string; poster_url: string | null;
  description: string | null; event_date: string | null; start_time: string | null;
  time_mode: "exact" | "approximate" | "tba";
  time_text: string | null; location_mode: "exact" | "approximate" | "tba";
  location_text: string | null;
  location: { title: string; address: string; map_link: string | null } | null;
  hosts: string | null; entry_fee: number; public_note: string | null;
  registration_status: "open" | "closed";
};

export type PublicSettings = {
  organization_name: string | null; telegram_support_link: string | null;
  bale_support_link: string | null; support_phone: string | null;
  card_number: string | null; account_holder: string | null;
};

export type PublicPage = { items: PublicEvent[]; total: number; limit: number; offset: number };
export type PublicStats = { cafe_count: number; guest_count: number; event_count: number };

async function getPublic<T>(path: string): Promise<T | null> {
  const origin = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${origin}/api/public${path}`, { cache: "no-store" });
    return response.ok ? await response.json() as T : null;
  } catch { return null; }
}

export const publicEvents = {
  list: (period: "upcoming" | "archive", offset = 0, limit = 20) =>
    getPublic<PublicPage>(`/events?period=${period}&offset=${offset}&limit=${limit}`),
  get: (id: number) => getPublic<PublicEvent>(`/events/${id}`),
  settings: () => getPublic<PublicSettings>("/settings/public"),
  stats: () => getPublic<PublicStats>("/stats"),
};

export function eventTime(event: PublicEvent): string {
  if (event.time_mode === "exact" && event.event_date && event.start_time)
    return `${formatJalali(`${event.event_date}T12:00:00Z`)}، ساعت ${persianDigits(event.start_time.slice(0, 5))}`;
  if (event.time_mode === "approximate") return persianDigits(event.time_text || "زمان به‌زودی اعلام می‌شود");
  return "زمان به‌زودی اعلام می‌شود";
}

export function eventPlace(event: PublicEvent): string {
  return event.location_mode === "exact" && event.location
    ? event.location.title : event.location_text || "مکان به‌زودی اعلام می‌شود";
}

export function eventFee(event: PublicEvent): string {
  return event.entry_fee === 0 ? "رایگان" : formatToman(event.entry_fee);
}

export function safeExternalUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch { return null; }
}
