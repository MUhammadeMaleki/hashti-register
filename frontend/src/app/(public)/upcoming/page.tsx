import Link from "next/link";
import { PublicEventCard } from "@/components/public-event-card";
import { publicEvents } from "@/lib/public-events";

export default async function Upcoming({ searchParams }: {
  searchParams: Promise<{ page?: string }>;
}) {
  const { page: rawPage } = await searchParams;
  const page = Math.max(1, Number.parseInt(rawPage ?? "1", 10) || 1);
  const results = await publicEvents.list("upcoming", (page - 1) * 20);
  return <>
    <section className="public-section"><p className="eyebrow">رویدادهای پیش‌رو</p>
      <h1>هشتی‌های آینده</h1>
      {results?.items.length ? <div className="public-event-grid">
        {results.items.map((event) => <PublicEventCard key={event.id} event={event} />)}
      </div> : <p className="public-empty">رویدادی در این صفحه نیست.</p>}
      <nav className="pagination" aria-label="صفحات رویدادها">
        {page > 1 && <Link className="text-link" href={`/upcoming?page=${page - 1}`}>صفحهٔ قبل</Link>}
        <span>صفحهٔ {page}</span>
        {results && page * 20 < results.total &&
          <Link className="text-link" href={`/upcoming?page=${page + 1}`}>صفحهٔ بعد</Link>}
      </nav></section>
  </>;
}
