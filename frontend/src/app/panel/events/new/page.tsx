import { AppShell } from "@/components/app-shell";
import { EventEditor } from "@/components/events/event-editor";

export default function NewEventPage() {
  return <AppShell kind="user"><EventEditor /></AppShell>;
}
