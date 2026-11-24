import { notFound } from "next/navigation";
import { GuestProfileView } from "@/components/guests/guest-profile";

export default async function GuestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const guestId = Number(id);
  if (!Number.isSafeInteger(guestId) || guestId < 1) notFound();
  return <GuestProfileView guestId={guestId} />;
}
