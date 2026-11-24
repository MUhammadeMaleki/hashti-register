import { AppShell } from "@/components/app-shell";
import { LocationManager } from "@/components/events/location-manager";

export default function LocationsPage() {
  return <AppShell kind="user"><LocationManager /></AppShell>;
}
