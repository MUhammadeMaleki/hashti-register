import Link from "next/link";
import { eventFee, eventPlace, eventTime, type PublicEvent } from "@/lib/public-events";

export function FeaturedEventCard({ event, index }: { event: PublicEvent; index: number }) {
  return <article className={`featured-event-card featured-event-card-${index % 3}`}>
    <Link href={`/events/${event.id}`} className="featured-event-image" aria-label={`جزئیات ${event.title}`}>
      {event.poster_url
        ? <img src={event.poster_url} alt={`پوستر ${event.title}`} loading="lazy" />
        : <span className="featured-event-image-fallback" aria-hidden="true">هشتی<span>.</span></span>}
      <span className="featured-event-number">هشتی شمارهٔ {new Intl.NumberFormat("fa-IR").format(event.event_number)}</span>
      <span className={`featured-event-status ${event.registration_status === "open" ? "is-open" : ""}`}>
        {event.registration_status === "open" ? "ثبت‌نام باز" : "ثبت‌نام بسته"}
      </span>
    </Link>
    <div className="featured-event-content">
      <h3><Link href={`/events/${event.id}`}>{event.title}</Link></h3>
      {event.description && <p className="featured-event-description">{event.description}</p>}
      <dl className="featured-event-facts">
        <div><dt>زمان</dt><dd>{eventTime(event)}</dd></div>
        <div><dt>مکان</dt><dd>{eventPlace(event)}</dd></div>
        {event.hosts && <div><dt>میزبان</dt><dd>{event.hosts}</dd></div>}
        <div><dt>هزینهٔ ورود</dt><dd>{eventFee(event)}</dd></div>
      </dl>
      <Link className="featured-event-action" href={`/events/${event.id}`}>
        جزئیات هشتی <span aria-hidden="true">←</span>
      </Link>
    </div>
  </article>;
}
