import { api } from "@/lib/api";

export type InterestTag = { id: number; name: string };
export type GuestSummary = {
  id: number; first_name: string; last_name: string; phone: string;
  age: number | null; gender: string | null; education: string | null;
  internal_note: string | null; debt_ceiling: number | null;
  wallet_balance: number | null; has_account: boolean;
  created_at: string; updated_at: string;
};
export type GuestNote = { id: number; type: "general" | "financial";
  text: string; created_at: string; created_by: string };
export type GuestRegistration = {
  id: number; status: string; attendance: string; source: string; created_at: string;
  event: { id: number; event_number: number; title: string;
    event_date: string | null; hosts: string | null; secretaries: string[];
    is_cancelled: boolean };
  charges: { id: number; type: string; description: string;
    amount: number; is_cancelled: boolean }[];
  active_charge_total: number; settled_total: number; outstanding_total: number;
};
export type GuestProfile = GuestSummary & {
  finance_overview: { total_debt: number; net_debt: number;
    debt_ceiling: number | null; over_ceiling: boolean };
  tags: InterestTag[]; notes: GuestNote[]; registrations: GuestRegistration[];
  wallet_transactions: { id: number; type: string; amount: number;
    registration_id: number | null; note: string; reason: string | null;
    original_transaction_id: number | null; actor_name: string | null;
    created_at: string }[];
  payments: { id: number; amount: number; status: string;
    event_id: number | null; created_at: string }[];
};
export type GuestInput = {
  first_name: string; last_name: string; phone: string;
  age: number | null; gender: string | null; education: string | null;
  internal_note: string | null; debt_ceiling: number | null;
};
export type GuestPage = { items: GuestSummary[]; total: number; limit: number; offset: number };
export type GuestListFilters = { interestTagId?: number; ageMin?: number; ageMax?: number;
  gender?: string };

export const guestsApi = {
  list: (q = "", offset = 0, filters: GuestListFilters = {}) => {
    const params = new URLSearchParams({ q, offset: String(offset), limit: "30" });
    if (filters.interestTagId) params.set("interest_tag_id", String(filters.interestTagId));
    if (filters.ageMin !== undefined) params.set("age_min", String(filters.ageMin));
    if (filters.ageMax !== undefined) params.set("age_max", String(filters.ageMax));
    if (filters.gender) params.set("gender", filters.gender);
    return api<GuestPage>(`/admin/guests?${params}`);
  },
  filterOptions: () => api<{ genders: string[] }>("/admin/guests/filter-options"),
  get: (id: number) => api<GuestProfile>(`/admin/guests/${id}`),
  create: (body: GuestInput) => api<GuestProfile>("/admin/guests", {
    method: "POST", body: JSON.stringify(body),
  }),
  update: (id: number, body: Partial<GuestInput>) => api<GuestProfile>(`/admin/guests/${id}`, {
    method: "PATCH", body: JSON.stringify(body),
  }),
  remove: (id: number) => api<void>(`/admin/guests/${id}`, { method: "DELETE" }),
  tags: () => api<InterestTag[]>("/admin/interest-tags"),
  createTag: (name: string) => api<InterestTag>("/admin/interest-tags", {
    method: "POST", body: JSON.stringify({ name }),
  }),
  setTags: (id: number, tag_ids: number[]) => api<GuestProfile>(
    `/admin/guests/${id}/tags`, { method: "PUT", body: JSON.stringify({ tag_ids }) }),
  addNote: (id: number, type: "general" | "financial", text: string) =>
    api<GuestNote>(`/admin/guests/${id}/notes`, {
      method: "POST", body: JSON.stringify({ type, text }),
    }),
  adjustWallet: (id: number, amount: number, note: string) =>
    api<{ wallet_balance: number }>(`/admin/finance/guests/${id}/adjustments`, {
      method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ amount, note }),
    }),
  settle: (registrationId: number, amount: number) =>
    api<{ debt: number; wallet_balance: number }>(
      `/admin/finance/registrations/${registrationId}/settlements`, {
        method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ amount }),
      }),
  settlements: (registrationId: number) => api<{
    id: number; amount: number; active_amount: number; created_at: string
  }[]>(`/admin/finance/registrations/${registrationId}/settlements`),
  refund: (settlementId: number, amount: number, reason: string) =>
    api<{ debt: number; wallet_balance: number }>(
      `/admin/finance/settlements/${settlementId}/refunds`, {
        method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ amount, reason }),
      }),
};
