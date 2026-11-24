import { PublicFooter } from "@/components/public-footer";
import { PublicHeader } from "@/components/public-header";

export default function PublicLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <main className="home public-home home-landing public-site">
    <PublicHeader />
    {children}
    <PublicFooter />
  </main>;
}
