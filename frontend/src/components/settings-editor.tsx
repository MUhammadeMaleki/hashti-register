"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button, Field } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { latinDigits, persianDigits } from "@/lib/format";
import { useSession } from "@/hooks/use-session";

type Values = { card_number?: string; default_debt_ceiling?: number };

export function SettingsEditor() {
  const { session, loading } = useSession();
  const [original, setOriginal] = useState<Values>({});
  const [cardNumber, setCardNumber] = useState("");
  const [debtCeiling, setDebtCeiling] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (session?.role !== "super_admin") return;
    let active = true;
    api<Values>("/admin/settings").then((values) => {
      if (!active) return;
      setOriginal(values);
      setCardNumber(persianDigits(latinDigits(values.card_number ?? "")));
      setDebtCeiling(values.default_debt_ceiling === undefined ?
        "" : persianDigits(String(values.default_debt_ceiling)));
    }).catch((caught) => { if (active) setError(errorMessage(caught)); });
    return () => { active = false; };
  }, [session?.role]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const card = latinDigits(cardNumber.trim());
    const ceiling = latinDigits(debtCeiling.trim());
    if (card.length > 32 || (ceiling !== "" &&
      (!/^\d+$/.test(ceiling) || !Number.isSafeInteger(Number(ceiling))))) {
      setError("شماره کارت باید حداکثر ۳۲ نویسه و سقف بدهی عدد صحیح نامنفی باشد.");
      return;
    }
    if (ceiling === "" && original.default_debt_ceiling !== undefined) {
      setError("برای تغییر سقف عمومی، عدد نامنفی وارد کنید؛ حذف سقف در این نسخه پشتیبانی نمی‌شود.");
      return;
    }
    const changes: Values = {};
    if (card !== latinDigits(original.card_number ?? "")) changes.card_number = card;
    if (ceiling !== "" && Number(ceiling) !== original.default_debt_ceiling)
      changes.default_debt_ceiling = Number(ceiling);
    if (Object.keys(changes).length === 0) {
      setError(""); setNotice("تغییری برای ذخیره وجود ندارد."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api<Values>("/admin/settings", {
        method: "PATCH", body: JSON.stringify(changes),
      });
      const current = await api<Values>("/admin/settings");
      setOriginal(current);
      setCardNumber(persianDigits(latinDigits(current.card_number ?? "")));
      setDebtCeiling(current.default_debt_ceiling === undefined ?
        "" : persianDigits(String(current.default_debt_ceiling)));
      setNotice("تنظیمات ذخیره شد.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  if (loading) return <p role="status">در حال بررسی دسترسی…</p>;
  if (session?.role !== "super_admin")
    return <p className="alert error">تنظیمات فقط برای مدیر هشتی در دسترس است.</p>;
  return <section className="management-panel management-finance" aria-labelledby="management-finance-title">
    <div className="management-panel-heading"><div><span>تنظیمات مالی</span>
      <h3 id="management-finance-title">شماره کارت و سقف بدهی</h3>
      <p>این مقادیر برای همهٔ هشتی‌ها اعمال می‌شوند.</p></div></div>
      <form className="management-finance-form" onSubmit={save}>
        <Field id="settings-card-number" label="شماره کارت هشتی"
          inputMode="numeric" dir="ltr" maxLength={32} value={cardNumber}
          onChange={(event) => setCardNumber(persianDigits(latinDigits(event.target.value)))}
          hint="این شماره در صفحهٔ عمومی رویداد نمایش داده می‌شود." />
        <Field id="settings-debt-ceiling" label="سقف عمومی بدهی (تومان)"
          inputMode="numeric" pattern="[۰-۹0-9]*" value={debtCeiling}
          onChange={(event) => setDebtCeiling(persianDigits(latinDigits(event.target.value)
            .replace(/[^0-9]/g, "")))}
          hint="اگر تاکنون تعیین نشده، خالی بماند. عبور از سقف فقط هشدار می‌دهد." />
        <Button type="submit" className="primary" disabled={busy}>
          {busy ? "در حال ذخیره…" : "ذخیره تنظیمات"}</Button>
      </form>
      {error && <p className="alert error" role="alert">{error}</p>}
      {notice && <p className="alert success" role="status">{notice}</p>}
  </section>;
}
