import { api } from "@/lib/api";

export type RegistrationMember = { first_name: string; last_name: string; phone: string };
export type RegistrationResult = { index: number; status: "created" | "error";
  registration_id?: number; code?: string };
export type Attendance = "pending" | "present" | "absent_kept" | "absent_forfeited";
export type EventRegistration = {
  id: number; guest_id: number; first_name: string; last_name: string; phone: string;
  status: "active" | "cancelled"; attendance: Attendance;
  active_charge_total: number; active_settlements: number;
  debt: number; wallet_balance: number;
  event_payments: { id: number; amount: number;
    status: "pending" | "approved" | "rejected"; created_at: string }[];
};
export type Charge = { id: number; type: "entry" | "order"; description: string;
  amount: number; is_cancelled: boolean };

export const registrationsApi = {
  publicGroup: (eventId: number, members: RegistrationMember[]) =>
    api<{ results: RegistrationResult[] }>(`/public/events/${eventId}/register`, {
      method: "POST", body: JSON.stringify({ members }),
    }),
  adminAdd: (eventId: number, body: { guest_id: number } | RegistrationMember) =>
    api<{ id: number; event_id: number; status: string; attendance: string }>(
      `/admin/events/${eventId}/registrations`, {
        method: "POST", body: JSON.stringify(body),
      }),
  eventList: (eventId: number, offset = 0) =>
    api<{ items: EventRegistration[]; total: number; limit: number; offset: number }>(
      `/admin/events/${eventId}/registrations?offset=${offset}&limit=50`),
  setAttendance: (registrationId: number, attendance: Attendance, key: string) =>
    api<{ registration_id: number; attendance: Attendance; changed: boolean;
      debt: number; wallet_balance: number }>(
      `/admin/registrations/${registrationId}/attendance`, {
        method: "POST", headers: { "Idempotency-Key": key },
        body: JSON.stringify({ attendance }),
      }),
  cancel: (registrationId: number) => api<{ registration_id: number; changed: boolean;
    refunded_total: number }>(`/admin/registrations/${registrationId}/cancel`, {
      method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
    }),
  reactivate: (registrationId: number) => api<{ registration_id: number; changed: boolean;
    attendance: Attendance }>(`/admin/registrations/${registrationId}/reactivate`, {
      method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
    }),
  charges: (registrationId: number) =>
    api<Charge[]>(`/admin/registrations/${registrationId}/charges`),
  createOrder: (registrationId: number, description: string, amount: number) =>
    api<{ id: number }>(`/admin/registrations/${registrationId}/orders`, {
      method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ description, amount }),
    }),
  updateOrder: (registrationId: number, chargeId: number, description: string, amount: number) =>
    api<{ id: number }>(`/admin/registrations/${registrationId}/orders/${chargeId}`, {
      method: "PATCH", headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ description, amount }),
    }),
  cancelOrder: (registrationId: number, chargeId: number) =>
    api<{ id: number }>(`/admin/registrations/${registrationId}/orders/${chargeId}`, {
      method: "DELETE", headers: { "Idempotency-Key": crypto.randomUUID() },
    }),
};
