import type { Metadata } from "next";

import { LiveView } from "@/components/live-view";
import { PageIntro } from "@/components/page-intro";
import { ProductShell } from "@/components/product-shell";

export const metadata: Metadata = { title: "Live" };

export default function LivePage() {
  return (
    <ProductShell>
      <PageIntro
        eyebrow="Operational view"
        title="Live network"
        description="The current airline world and the factual impact of active disruptions."
      />
      <LiveView />
    </ProductShell>
  );
}
