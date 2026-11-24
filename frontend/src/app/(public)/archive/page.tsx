import Link from "next/link";
import { ArchiveEventCard } from "@/components/archive-event-card";
import { publicEvents } from "@/lib/public-events";

export default async function Archive({ searchParams }: {
  searchParams: Promise<{ page?: string }>;
}) {
  const pageSize = 20;
  const { page: rawPage } = await searchParams;
  const page = Math.max(1, Number.parseInt(rawPage ?? "1", 10) || 1);
  const results = await publicEvents.list("archive", (page - 1) * pageSize, pageSize);
  const total = results?.total ?? null;
  const pageCount = total === null ? 1 : Math.max(1, Math.ceil(total / pageSize));
  const formatCount = (count: number) => new Intl.NumberFormat("fa-IR").format(count);
  return <>
    <section className="archive-hero" aria-labelledby="archive-title">
      <div className="archive-hero-copy">
        <span className="archive-hero-kicker">دفتر خاطره‌های هشتی</span>
        <h1 id="archive-title">این‌همه بار،<br /><span>دور هم نشستیم.</span></h1>
        <p>هر هشتی یک گفت‌وگوی تازه بود؛ هر گفت‌وگو، ردّی از آدم‌هایی که کنار هم نشستند.</p>
        <span className="archive-hero-caption">هشتی‌های گذشته را ورق بزنیم <span aria-hidden="true">↙</span></span>
      </div>
      <div className="archive-hero-stat" aria-label={total === null ? "تعداد هشتی‌های گذشته در دسترس نیست" : `${formatCount(total)} هشتی گذشته`}>
        <span className="archive-hero-count">{total === null ? "—" : formatCount(total)}</span>
        <span className="archive-hero-unit">بار هشتی رفتیم</span>
      </div>
    </section>
    <section className="public-section archive-collection" aria-labelledby="archive-collection-title">
      <div className="archive-collection-heading">
        <div><span className="archive-collection-kicker">از تازه‌ترین خاطره به عقب</span>
          <h2 id="archive-collection-title">دفتر هشتی‌ها</h2></div>
        <p>{results ? `${formatCount(pageSize)} هشتی در هر صفحه · ${formatCount(results.total)} هشتی در آرشیو` :
          "آرشیو موقتاً در دسترس نیست"}</p>
      </div>
      {results?.items.length ? <div className="archive-event-grid">
        {results.items.map((event) => <ArchiveEventCard key={event.id} event={event} />)}
      </div> : <p className="public-empty">رویدادی در این صفحه نیست.</p>}
      {results && pageCount > 1 && <nav className="archive-pagination" aria-label="صفحات آرشیو">
        {page > 1 ? <Link href={`/archive?page=${page - 1}`}>→ صفحهٔ قبل</Link> : <span />}
        <span className="archive-pagination-current">صفحهٔ {formatCount(page)} از {formatCount(pageCount)}</span>
        {page < pageCount ? <Link href={`/archive?page=${page + 1}`}>صفحهٔ بعد ←</Link> : <span />}
      </nav>}
    </section>
  </>;
}
