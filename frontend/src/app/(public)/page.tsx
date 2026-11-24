import Link from "next/link";
import { ArchiveEventCard } from "@/components/archive-event-card";
import { FeaturedEventsSlider } from "@/components/featured-events-slider";
import { publicEvents } from "@/lib/public-events";

export default async function Home() {
  const [upcoming, archive, stats] = await Promise.all([
    publicEvents.list("upcoming", 0, 100), publicEvents.list("archive", 0, 100), publicEvents.stats(),
  ]);
  const featuredEvents = [...(upcoming?.items ?? [])]
    .sort((a, b) => b.event_number - a.event_number);
  const formatCount = (count: number | undefined) =>
    count === undefined ? "—" : new Intl.NumberFormat("fa-IR").format(count);
  return <>
    <section className="public-section featured-section" aria-labelledby="featured-title">
      <div className="featured-heading">
        <p className="featured-kicker">گفت‌وگو در کافه‌ها</p>
        <h1 id="featured-title"><span>جدیدترین هشتی‌ها</span></h1>
        <p>صندلی‌ات را رزرو کن، وارد هشتی شو و بیا راجع‌بهش حرف بزنیم.</p>
      </div>
      {featuredEvents.length ? <FeaturedEventsSlider events={featuredEvents} />
        : <p className="public-empty">هنوز هشتی‌ای برای نمایش وجود ندارد.</p>}
      <div className="featured-stats" aria-label="هشتی در یک نگاه">
        <div><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 8h12v7a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V8ZM16 9h2a3 3 0 1 1 0 6h-2M3 21h15M8 3v2M12 3v2" /></svg><strong>{formatCount(stats?.cafe_count)}</strong><span>تعداد کافه‌ها</span></div>
        <div><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="9" cy="8" r="3" /><path d="M3 20v-2a6 6 0 0 1 12 0v2M17 5a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v2" /></svg><strong>{formatCount(stats?.guest_count)}</strong><span>تعداد هشتی‌نشین‌ها</span></div>
        <div><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18M8 15h3M8 18h7" /></svg><strong>{formatCount(stats?.event_count)}</strong><span>تعداد هشتی‌ها</span></div>
        <div><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg><strong>۳ سال</strong><span>مدت فعالیت</span></div>
      </div>
    </section>
    <section className="public-section"><div className="section-heading"><div>
      <p className="eyebrow">آرشیو</p><h2>هشتی‌های گذشته</h2></div>
      <Link className="archive-link" href="/archive">دیدن همهٔ آرشیو <span aria-hidden="true">←</span></Link></div>
      {archive?.items.length ? <div className="archive-event-grid">
        {archive.items.slice(0, 3).map((event) => <ArchiveEventCard key={event.id} event={event} />)}
      </div> : <p className="public-empty">هنوز رویدادی در آرشیو نیست.</p>}
    </section>
  </>;
}
