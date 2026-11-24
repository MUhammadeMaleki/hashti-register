"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AppShell } from "@/components/app-shell";
import { Button, Field } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatToman, persianDigits } from "@/lib/format";
import { guestsApi, type GuestListFilters, type GuestPage, type InterestTag } from "@/lib/guests";

const ageRanges = [
  { value: "all", label: "همهٔ سن‌ها" },
  { value: "0-17", label: "زیر ۱۸ سال" },
  { value: "18-24", label: "۱۸ تا ۲۴ سال" },
  { value: "25-34", label: "۲۵ تا ۳۴ سال" },
  { value: "35-44", label: "۳۵ تا ۴۴ سال" },
  { value: "45-59", label: "۴۵ تا ۵۹ سال" },
  { value: "60-130", label: "۶۰ سال به بالا" },
] as const;

export default function GuestsPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [interestTagId, setInterestTagId] = useState(0);
  const [ageRange, setAgeRange] = useState("all");
  const [gender, setGender] = useState("");
  const [tags, setTags] = useState<InterestTag[]>([]);
  const [genders, setGenders] = useState<string[]>([]);
  const [page, setPage] = useState<GuestPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([guestsApi.tags(), guestsApi.filterOptions()]).then(([allTags, options]) => {
      if (active) { setTags(allTags); setGenders(options.genders); }
    }).catch((caught) => { if (active) setError(errorMessage(caught)); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    const range = ageRange === "all" ? null : ageRange.split("-").map(Number);
    const filters: GuestListFilters = {
      interestTagId: interestTagId || undefined,
      ageMin: range?.[0], ageMax: range?.[1], gender: gender || undefined,
    };
    setLoading(true);
    guestsApi.list(activeQuery, offset, filters).then((result) => {
      if (active) { setPage(result); setError(""); }
    }).catch((caught) => { if (active) setError(errorMessage(caught)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [activeQuery, offset, interestTagId, ageRange, gender]);

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setOffset(0); setActiveQuery(query.trim());
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError("");
    try {
      const guest = await guestsApi.create({
        first_name: firstName.trim(), last_name: lastName.trim(), phone,
        age: null, gender: null, education: null, internal_note: null, debt_ceiling: null,
      });
      router.push(`/panel/guests/${guest.id}`);
    } catch (caught) { setError(errorMessage(caught)); setBusy(false); }
  }

  return <AppShell kind="user"><div className="residents-page">
    <section className="residents-intro" aria-labelledby="residents-title">
      <div><span>آدم‌های دور میز</span><h2 id="residents-title">بانک هشتی‌نشین‌ها</h2>
        <p>آدم‌ها، علاقه‌ها و سوابق هر هشتی‌نشین، همه در یک جا.</p></div>
      <div className="residents-intro-actions"><Link className="button secondary" href="/panel/import">ورود گروهی</Link>
        <Button type="button" className="primary" onClick={() => setShowNew(!showNew)}
          aria-expanded={showNew} aria-controls="new-resident-form">
          {showNew ? "بستن فرم" : "افزودن هشتی‌نشین"}</Button></div>
    </section>
    {error && <p className="alert error" role="alert">{error}</p>}
    {showNew && <section className="residents-new" id="new-resident-form" aria-labelledby="new-resident-title">
      <div><span>ثبت عضو تازه</span><h3 id="new-resident-title">هشتی‌نشین جدید</h3></div>
      <form className="residents-new-form" onSubmit={create}>
        <Field id="guest-first" label="نام" required value={firstName}
          onChange={(event) => setFirstName(event.target.value)} />
        <Field id="guest-last" label="نام خانوادگی" required value={lastName}
          onChange={(event) => setLastName(event.target.value)} />
        <Field id="guest-phone" label="شماره موبایل" required inputMode="tel" value={phone}
          onChange={(event) => setPhone(event.target.value)} />
        <Button type="submit" className="primary" disabled={busy}>
          {busy ? "در حال ثبت…" : "ساخت پروفایل"}</Button>
      </form>
    </section>}
    <section className="residents-directory" aria-label="فهرست هشتی‌نشین‌ها">
      <div className="residents-directory-heading"><div><span>فهرست آدم‌ها</span><h3>هشتی‌نشین‌ها</h3></div>
        <span>{page ? `${page.total.toLocaleString("fa-IR")} نفر` : "—"}</span></div>
      <form className="residents-filters" onSubmit={search}>
        <label className="residents-search"><span>جست‌وجو</span><div><input value={query}
          onChange={(event) => setQuery(event.target.value)} placeholder="نام یا شماره موبایل…" />
          <Button type="submit" className="primary">جست‌وجو</Button></div></label>
        <label><span>علاقه</span><select value={interestTagId} onChange={(event) => {
          setOffset(0); setInterestTagId(Number(event.target.value));
        }}><option value={0}>همهٔ علاقه‌ها</option>{tags.map((tag) =>
          <option value={tag.id} key={tag.id}>{tag.name}</option>)}</select></label>
        <label><span>رنج سنی</span><select value={ageRange} onChange={(event) => {
          setOffset(0); setAgeRange(event.target.value);
        }}>{ageRanges.map((range) => <option value={range.value} key={range.value}>{range.label}</option>)}</select></label>
        <label><span>جنسیت</span><select value={gender} onChange={(event) => {
          setOffset(0); setGender(event.target.value);
        }}><option value="">همهٔ جنسیت‌ها</option>{genders.map((value) =>
          <option value={value} key={value}>{value}</option>)}</select></label>
      </form>
      {loading ? <p className="residents-empty" role="status">در حال دریافت هشتی‌نشین‌ها…</p> :
        page?.items.length ? <div className="residents-list">{page.items.map((guest) =>
          <article className="resident-row" key={guest.id}>
            <div className="resident-avatar" aria-hidden="true">{guest.first_name[0]}{guest.last_name[0]}</div>
            <div className="resident-identity"><h4>{guest.first_name} {guest.last_name}</h4>
              <span>شناسهٔ {guest.id.toLocaleString("fa-IR")}</span></div>
            <div className="resident-detail"><small>شماره موبایل</small>
              <span dir="ltr">{persianDigits(guest.phone)}</span></div>
            <div className="resident-detail"><small>سن و جنسیت</small>
              <span>{guest.age === null ? "سن نامشخص" : `${guest.age.toLocaleString("fa-IR")} سال`}
                {guest.gender ? ` · ${guest.gender}` : ""}</span></div>
            <div className="resident-detail"><small>کیف پول</small>
              <span>{guest.wallet_balance === null ? "—" : formatToman(guest.wallet_balance)}</span></div>
            <div className="resident-row-end"><span className={guest.has_account ? "has-account" : ""}>
              {guest.has_account ? "حساب فعال" : "بدون حساب"}</span>
              <Link href={`/panel/guests/${guest.id}`} aria-label={`پروفایل ${guest.first_name} ${guest.last_name}`}>پروفایل ←</Link></div>
          </article>)}</div> : <p className="residents-empty">هشتی‌نشینی با این جست‌وجو و فیلترها پیدا نشد.</p>}
      {!loading && page && page.total > 30 && <nav className="residents-pagination" aria-label="صفحات هشتی‌نشین‌ها">
        <Button type="button" className="secondary" disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 30))}>صفحهٔ قبل</Button>
        <span>صفحهٔ {(Math.floor(offset / 30) + 1).toLocaleString("fa-IR")} از {Math.ceil(page.total / 30).toLocaleString("fa-IR")}</span>
        <Button type="button" className="secondary" disabled={offset + 30 >= page.total}
          onClick={() => setOffset(offset + 30)}>صفحهٔ بعد</Button>
      </nav>}
    </section>
  </div></AppShell>;
}
