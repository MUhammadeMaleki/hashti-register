import { api } from "@/lib/api";

export type MyFinance = {
  wallet_balance: number;
  registrations: { id: number; event_id: number; event_number: number;
    title: string; poster_url: string | null; event_date: string | null;
    start_time: string | null; time_mode: "exact" | "approximate" | "tba";
    time_text: string | null; location_mode: "exact" | "approximate" | "tba";
    location_text: string | null; location_title: string | null; entry_fee: number;
    attendance: string; is_cancelled: boolean;
    active_charges: number; active_settlements: number; active_discounts: number;
    debt: number }[];
  transactions: { id: number; type: string; amount: number;
    registration_id: number | null; note: string; created_at: string }[];
};

export type GuestProfile = {
  id: number; first_name: string; last_name: string; phone: string;
  age: number | null; gender: string | null; education: string | null;
};

export type WalletTransaction = MyFinance["transactions"][number];

export const financeApi = {
  mine: () => api<MyFinance>("/me/finance"),
  profile: () => api<GuestProfile>("/me/profile"),
  transactions: () => api<WalletTransaction[]>("/me/wallet/transactions"),
  settleMine: (registrationId: number, amount: number) =>
    api<{ debt: number; wallet_balance: number }>(
      `/me/registrations/${registrationId}/settlements`, {
        method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ amount }),
      }),
};
