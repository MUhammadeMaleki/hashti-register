import { api } from "@/lib/api";

export type EventImportError = { row: number; reason: string };
export type EventPreviewRow = {
  row: number; event_number: number; title: string; event_date: string | null;
  start_time: string | null; description: string | null;
  location_name: string | null; location_address: string | null;
  entry_fee: number; public_note: string | null; registration_status: "open" | "closed";
};
export type EventImportPreview = {
  total: number; valid_count: number; error_count: number;
  preview_rows: EventPreviewRow[]; errors: EventImportError[]; preview_token: string;
};
export type EventImportResult = {
  total: number; imported_count: number; error_count: number; errors: EventImportError[];
};

export const eventImportApi = {
  preview(file: File) {
    const body = new FormData(); body.set("file", file);
    return api<EventImportPreview>("/admin/import/events/preview", { method: "POST", body });
  },
  confirm(file: File, token: string) {
    const body = new FormData(); body.set("file", file); body.set("preview_token", token);
    return api<EventImportResult>("/admin/import/events/confirm", { method: "POST", body });
  },
};
