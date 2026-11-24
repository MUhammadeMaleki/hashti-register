"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AppShell } from "@/components/app-shell";
import { Button, Card } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { persianDigits } from "@/lib/format";
import { guestImportApi, type ImportPreview, type ImportResult } from "@/lib/guest-import";

export default function GuestImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function inspect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || busy) return;
    setBusy(true); setError(""); setPreview(null); setResult(null);
    try { setPreview(await guestImportApi.preview(file)); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function confirm() {
    if (!file || !preview || busy) return;
    setBusy(true); setError("");
    try { setResult(await guestImportApi.confirm(file, preview.preview_token)); setPreview(null); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  const errors = result?.errors ?? preview?.errors ?? [];
  return <AppShell kind="user"><div className="editor-stack">
    <div className="section-heading"><div><h2>ورود گروهی هشتی‌نشین‌ها</h2>
      <p className="muted">هشتی‌نشین‌ها بدون هشتی و حساب ورود ساخته می‌شوند؛ کیف پولشان صفر است.</p></div>
      <Link className="button secondary" href="/panel/guests">بازگشت به بانک هشتی‌نشین‌ها</Link>
    </div>
    {error && <p className="alert error" role="alert">{error}</p>}
    <Card title="فایل Excel"><p>ستون‌های نام، نام خانوادگی و شماره موبایل الزامی‌اند.
      شماره موبایل را در Excel به‌صورت متن نگه دارید. حداکثر ۵۰۰۰ ردیف و ۳ مگابایت.</p>
      <a className="button secondary" href="/api/admin/import/template">دریافت فایل نمونه</a>
      <form className="form-stack" onSubmit={inspect}>
        <div className="field"><label htmlFor="guest-import-file">فایل XLSX</label>
          <input id="guest-import-file" type="file" accept=".xlsx" required
            onChange={(event) => { setFile(event.target.files?.[0] ?? null);
              setPreview(null); setResult(null); setError(""); }} /></div>
        <Button type="submit" className="primary" disabled={!file || busy}>
          {busy ? "در حال بررسی…" : "بررسی و پیش‌نمایش"}</Button>
      </form>
    </Card>
    {preview && <Card title="پیش‌نمایش پیش از ورود">
      <p>{preview.total.toLocaleString("fa-IR")} ردیف بررسی شد؛
        {" "}{preview.valid_count.toLocaleString("fa-IR")} معتبر و
        {" "}{preview.error_count.toLocaleString("fa-IR")} دارای خطا.</p>
      <p className="muted">حداکثر ۱۰۰ ردیف معتبر اول نمایش داده می‌شود. تأیید، همهٔ ردیف‌های معتبر را وارد می‌کند.</p>
      <div className="table-scroll"><table><thead><tr><th>ردیف</th><th>نام</th>
        <th>نام خانوادگی</th><th>موبایل</th><th>سن</th></tr></thead><tbody>
        {preview.preview_rows.map((row) => <tr key={row.row}>
          <td>{row.row.toLocaleString("fa-IR")}</td><td>{row.first_name}</td><td>{row.last_name}</td>
          <td dir="ltr">{persianDigits(row.phone)}</td>
          <td>{row.age === null ? "—" : row.age.toLocaleString("fa-IR")}</td>
        </tr>)}</tbody></table></div>
      <Button type="button" className="primary" disabled={busy || !preview.valid_count}
        onClick={confirm}>{busy ? "در حال ورود…" : "تأیید ورود ردیف‌های معتبر"}</Button>
    </Card>}
    {result && <Card title="نتیجه ورود"><p>از {result.total.toLocaleString("fa-IR")} ردیف،
      {" "}{result.imported_count.toLocaleString("fa-IR")} هشتی‌نشین وارد شد و
      {" "}{result.error_count.toLocaleString("fa-IR")} ردیف وارد نشد.</p></Card>}
    {!!errors.length && <Card title="خطاهای ردیفی"><div className="table-scroll">
      <table><thead><tr><th>ردیف Excel</th><th>دلیل</th></tr></thead><tbody>
        {errors.map((item) => <tr key={item.row}><td>{item.row.toLocaleString("fa-IR")}</td>
          <td>{item.reason}</td></tr>)}
      </tbody></table></div></Card>}
  </div></AppShell>;
}
