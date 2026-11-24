import { api } from "@/lib/api";

export type Payment = {
  id: number; amount: number; tracking_code: string | null; event_id: number | null;
  status: "pending" | "approved" | "rejected"; reject_reason: string | null;
  has_image: boolean; created_at: string;
};

export type AdminPayment = Payment & {
  guest_id: number; guest_name: string; event_title: string | null;
  reviewed_by: number | null; reviewed_at: string | null;
};

export type PaymentReview = {
  id: number; status: Payment["status"]; reject_reason: string | null;
  reviewed_by: number; reviewed_at: string;
  transaction_id: number | null; wallet_balance: number | null;
};

export const paymentsApi = {
  mine: () => api<Payment[]>("/me/payments"),
  submit: (amount: number, trackingCode: string, receipt: File | null, eventId: number | null) => {
    const body = new FormData();
    body.set("amount", String(amount));
    if (trackingCode.trim()) body.set("tracking_code", trackingCode.trim());
    if (receipt) body.set("receipt", receipt);
    const path = eventId === null ? "/me/payments" : `/me/events/${eventId}/payments`;
    return api<Payment>(path, {
      method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body,
    });
  },
  adminList: (status: Payment["status"], offset = 0) =>
    api<{ items: AdminPayment[]; total: number }>(
      `/admin/payments?status=${status}&limit=100&offset=${offset}`),
  adminDetail: (id: number) => api<AdminPayment>(`/admin/payments/${id}`),
  approve: (id: number) => api<PaymentReview>(`/admin/payments/${id}/approve`, {
    method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
  }),
  reject: (id: number, reason: string) => api<PaymentReview>(`/admin/payments/${id}/reject`, {
    method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ reason: reason.trim() || null }),
  }),
};
