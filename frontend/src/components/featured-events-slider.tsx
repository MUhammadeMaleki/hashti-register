"use client";

import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { FeaturedEventCard } from "@/components/featured-event-card";
import type { PublicEvent } from "@/lib/public-events";

export function FeaturedEventsSlider({ events }: { events: PublicEvent[] }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const [atEnd, setAtEnd] = useState(false);
  const [mobileIndex, setMobileIndex] = useState(0);
  const [transition, setTransition] = useState<{ from: number; to: number; direction: "next" | "previous"; fromX: number } | null>(null);
  const [dragX, setDragX] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ pointerId: number; x: number; y: number; dragging: boolean } | null>(null);
  const suppressClickRef = useRef(false);
  const transitionTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (transitionTimer.current) clearTimeout(transitionTimer.current);
  }, []);

  function moveMobile(direction: "next" | "previous", fromX: number) {
    if (transition || events.length < 2) return;
    const step = direction === "next" ? 1 : -1;
    const to = (mobileIndex + step + events.length) % events.length;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setMobileIndex(to);
      return;
    }
    setTransition({ from: mobileIndex, to, direction, fromX });
    transitionTimer.current = setTimeout(() => {
      setMobileIndex(to);
      setTransition(null);
      transitionTimer.current = null;
    }, 480);
  }

  function dragTransform(offset: number) {
    const progress = Math.min(Math.abs(offset) / (stageRef.current?.clientWidth || 320), 1);
    const lift = -Math.sin(progress * Math.PI * .8) * 32;
    const rotation = progress * (offset < 0 ? -19 : 19);
    return `translate3d(${offset}px, ${lift}px, 0) rotate(${rotation}deg)`;
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (transition || events.length < 2 || (event.pointerType === "mouse" && event.button !== 0)) return;
    dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, dragging: false };
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.dragging) {
      if (Math.abs(dx) < 8 || Math.abs(dx) <= Math.abs(dy) * 1.15) return;
      drag.dragging = true;
      event.currentTarget.setPointerCapture(event.pointerId);
      setIsDragging(true);
    }
    setDragX(Math.max(-event.currentTarget.clientWidth, Math.min(event.currentTarget.clientWidth, dx)));
  }

  function onPointerEnd(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (!drag.dragging) return;
    suppressClickRef.current = true;
    setTimeout(() => { suppressClickRef.current = false; }, 0);
    const dx = event.clientX - drag.x;
    setIsDragging(false);
    setDragX(0);
    if (event.type !== "pointercancel" && Math.abs(dx) > Math.min(65, event.currentTarget.clientWidth * .18)) {
      moveMobile(dx < 0 ? "next" : "previous", dx);
    }
  }

  function goTo(next: number) {
    const target = Math.max(0, Math.min(events.length - 1, next));
    trackRef.current?.children[target]?.scrollIntoView({
      behavior: "smooth", inline: "start", block: "nearest",
    });
    setIndex(target);
  }

  function syncIndex() {
    const track = trackRef.current;
    if (!track) return;
    const right = track.getBoundingClientRect().right;
    let closest = 0;
    let distance = Infinity;
    Array.from(track.children).forEach((child, position) => {
      const current = Math.abs(child.getBoundingClientRect().right - right);
      if (current < distance) { distance = current; closest = position; }
    });
    setIndex(closest);
    setAtEnd(-track.scrollLeft >= track.scrollWidth - track.clientWidth - 2);
  }

  return <div className="featured-events-slider">
    <div className="featured-event-track" ref={trackRef} onScroll={syncIndex}
      aria-label="جدیدترین هشتی‌ها">
      {events.map((event, position) =>
        <FeaturedEventCard key={event.id} event={event} index={position} />)}
    </div>
    <div className="featured-mobile-carousel">
      <div className="featured-mobile-stage" ref={stageRef} aria-label="جدیدترین هشتی‌ها"
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerEnd}
        onPointerCancel={onPointerEnd} onDragStart={(event) => event.preventDefault()}
        onClickCapture={(event) => {
          if (suppressClickRef.current) { event.preventDefault(); event.stopPropagation(); suppressClickRef.current = false; }
        }}>
        {transition ? <>
          <div className={`featured-mobile-slide is-entering-${transition.direction}`}>
            <FeaturedEventCard event={events[transition.to]} index={transition.to} />
          </div>
          <div className={`featured-mobile-slide is-leaving-${transition.direction}`} aria-hidden="true" inert
            style={{ "--drag-start": `${transition.fromX}px`, "--drag-transform": dragTransform(transition.fromX) } as CSSProperties}>
            <FeaturedEventCard event={events[transition.from]} index={transition.from} />
          </div>
        </> : <>
          {events.length > 1 && <div className="featured-mobile-slide is-preview" aria-hidden="true" inert>
            <FeaturedEventCard event={events[(mobileIndex + 1) % events.length]} index={(mobileIndex + 1) % events.length} />
          </div>}
          <div className={`featured-mobile-slide is-current${isDragging ? " is-dragging" : ""}`}
            style={{ transform: dragTransform(dragX) }}>
            <FeaturedEventCard event={events[mobileIndex]} index={mobileIndex} />
          </div>
        </>}
      </div>
      {events.length > 1 && <p className="featured-mobile-count" aria-live="polite">
        {new Intl.NumberFormat("fa-IR").format(mobileIndex + 1)} از {new Intl.NumberFormat("fa-IR").format(events.length)}
      </p>}
    </div>
    {events.length > 3 && <div className="featured-slider-controls">
      <span>برای دیدن هشتی‌های بیشتر ورق بزنید</span>
      <div className="featured-slider-arrows">
        <button type="button" onClick={() => goTo(index - 1)} disabled={index === 0}
          aria-label="هشتی قبلی">→</button>
        <button type="button" onClick={() => goTo(index + 1)} disabled={atEnd}
          aria-label="هشتی بعدی">←</button>
      </div>
    </div>}
  </div>;
}
