import { api } from "@/lib/api";

export type Secretary = { id: number; full_name: string; is_active?: boolean };
export type Location = { id: number; title: string; address: string;
  map_link: string | null; linked_event_count: number };
export type EventRecord = {
  id: number; event_number: number; title: string; description: string | null;
  poster_url: string | null;
  event_date: string | null; start_time: string | null; time_text: string | null;
  time_mode: "exact" | "approximate" | "tba";
  location_id: number | null; location_mode: "exact" | "approximate" | "tba";
  location_text: string | null; location: Location | null; hosts: string | null;
  entry_fee: number; capacity: number | null; public_note: string | null;
  registration_status: "open" | "closed"; is_cancelled: boolean;
  secretaries: Secretary[];
};
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type EventListFilters = {
  period?: "all" | "upcoming" | "archive" | "cancelled";
  registrationStatus?: "all" | "open" | "closed";
  search?: string;
};

export const eventsApi = {
  list: (offset = 0, limit = 20, filters: EventListFilters = {}) => {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (filters.period && filters.period !== "all") params.set("period", filters.period);
    if (filters.registrationStatus && filters.registrationStatus !== "all")
      params.set("registration_status", filters.registrationStatus);
    if (filters.search?.trim()) params.set("q", filters.search.trim());
    return api<Page<EventRecord>>(`/admin/events?${params}`);
  },
  get: (id: number) => api<EventRecord>(`/admin/events/${id}`),
  nextNumber: () => api<{ suggested_number: number }>("/admin/events/next-number"),
  create: (body: object) => api<EventRecord>("/admin/events", {
    method: "POST", body: JSON.stringify(body),
  }),
  update: (id: number, body: object) => api<EventRecord>(`/admin/events/${id}`, {
    method: "PATCH", body: JSON.stringify(body),
  }),
  updateEntryFee: (id: number, amount: number, key: string) =>
    api<{ event_id: number; entry_fee: number; changed: boolean;
      registrations: number; refunds: number }>(`/admin/events/${id}/entry-fee`, {
      method: "PATCH", headers: { "Idempotency-Key": key },
      body: JSON.stringify({ amount }),
    }),
  cancel: (id: number) => api<{ event_id: number; is_cancelled: boolean;
    changed: boolean; registrations: number; refunded_total: number }>(
    `/admin/events/${id}/cancel`, {
      method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
    }),
  reactivate: (id: number) => api<{ event_id: number; is_cancelled: boolean;
    changed: boolean; registrations: number; refunded_total: number }>(
    `/admin/events/${id}/reactivate`, {
      method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
    }),
  setSecretaries: (id: number, user_ids: number[]) =>
    api<EventRecord>(`/admin/events/${id}/secretaries`, {
      method: "PUT", body: JSON.stringify({ user_ids }),
    }),
  remove: (id: number) => api<void>(`/admin/events/${id}`, { method: "DELETE" }),
  uploadPoster: (id: number, file: File) => {
    const body = new FormData();
    body.append("poster", file);
    return api<EventRecord>(`/admin/events/${id}/poster`, { method: "POST", body });
  },
  secretaries: () => api<Secretary[]>("/admin/secretaries"),
  locations: (offset = 0, limit = 50) =>
    api<Page<Location>>(`/admin/locations?offset=${offset}&limit=${limit}`),
  allLocations: async () => {
    const results: Location[] = [];
    for (let offset = 0; ; offset += 200) {
      const page = await api<Page<Location>>(`/admin/locations?offset=${offset}&limit=200`);
      results.push(...page.items);
      if (results.length >= page.total) return results;
    }
  },
  createLocation: (body: { title: string; address: string; map_link: string | null }) =>
    api<Location>("/admin/locations", { method: "POST", body: JSON.stringify(body) }),
  updateLocation: (id: number, body: { title: string; address: string; map_link: string | null }) =>
    api<Location>(`/admin/locations/${id}`, {
      method: "PATCH", body: JSON.stringify(body),
    }),
  removeLocation: (id: number) => api<void>(`/admin/locations/${id}`, { method: "DELETE" }),
};
