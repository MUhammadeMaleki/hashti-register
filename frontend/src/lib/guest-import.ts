import { api } from "@/lib/api";

export type ImportError = { row: number; reason: string };
export type PreviewRow = {
  row: number; first_name: string; last_name: string; phone: string;
  age: number | null; gender: string | null; education: string | null;
  internal_note: string | null;
};
export type ImportPreview = {
  total: number; valid_count: number; error_count: number;
  preview_rows: PreviewRow[]; errors: ImportError[]; preview_token: string;
};
export type ImportResult = {
  total: number; imported_count: number; error_count: number; errors: ImportError[];
};

export const guestImportApi = {
  preview(file: File) {
    const body = new FormData(); body.set("file", file);
    return api<ImportPreview>("/admin/import/preview", { method: "POST", body });
  },
  confirm(file: File, token: string) {
    const body = new FormData(); body.set("file", file); body.set("preview_token", token);
    return api<ImportResult>("/admin/import/confirm", { method: "POST", body });
  },
};
