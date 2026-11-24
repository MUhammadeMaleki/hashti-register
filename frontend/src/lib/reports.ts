import { api } from "@/lib/api";

export type Dashboard = {
  guest_count: number; upcoming_event_count: number; upcoming_registration_count: number;
  pending_receipt_count: number; debtor_count: number; total_debt: number;
  held_event_count: number;
};
export type ReportOptions = {
  events: { id: number; event_number: number; title: string }[];
  interests: { id: number; name: string }[];
};
export type EventReport = {
  event: { id: number; event_number: number; title: string;
    event_date: string | null; is_cancelled: boolean };
  present_count: number; entry_total: number; orders_total: number;
  charges_total: number; settled_total: number; debt_total: number;
  unsettled_count: number;
  debtors: { guest_id: number; name: string; phone: string; registration_id: number;
    charges: number; settled: number; debt: number }[];
};
export type FinancialGuest = {
  guest_id: number; name: string; phone: string; wallet_balance: number;
  debt: number; net_debt: number; unsettled_events: number;
  last_transaction_at: string | null;
};
export type GuestReportRow = FinancialGuest & {
  attendance_count: number; absence_count: number; guest_kind: "new" | "returning";
};
export type ReportPage<T> = { items: T[]; total: number; limit: number; offset: number };
export type Charts = {
  attendance_buckets: Record<string, number>;
  trend: { date: string; count: number }[];
  new_vs_returning: { new: number; returning: number };
  attendance_ratio: { present: number; absent: number };
  absences: { kept: number; forfeited: number };
  popular_events: { event_id: number; title: string; count: number }[];
  interests: { name: string; count: number }[];
};
export type Reconciliation = {
  items: { wallet_id: number; guest_id: number; guest_name: string;
    cached_balance: number; ledger_balance: number; difference: number;
    matches: boolean }[];
  total: number; mismatch_count_on_page: number;
};

export const reportsApi = {
  dashboard: () => api<Dashboard>("/admin/reports/dashboard"),
  options: () => api<ReportOptions>("/admin/reports/options"),
  event: (id: number, search = "") => api<EventReport>(
    `/admin/reports/events/${id}?q=${encodeURIComponent(search)}`),
  finance: (search = "", debtorsOnly = false, offset = 0) =>
    api<ReportPage<FinancialGuest>>(`/admin/reports/finance?${new URLSearchParams({
      q: search, debtors_only: String(debtorsOnly), offset: String(offset), limit: "50",
    })}`),
  guests: (params: URLSearchParams) =>
    api<ReportPage<GuestReportRow>>(`/admin/reports/guests?${params}`),
  charts: (params: URLSearchParams) =>
    api<Charts>(`/admin/reports/charts?${params}`),
  reconciliation: () => api<Reconciliation>("/admin/finance/reconciliation?limit=100"),
};
