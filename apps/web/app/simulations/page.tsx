import type { Metadata } from "next";

import { PageIntro } from "@/components/page-intro";
import { ProductShell } from "@/components/product-shell";
import { SimulationsView } from "@/components/simulations-view";

export const metadata: Metadata = { title: "Simulations" };

export default function SimulationsPage() {
  return (
    <ProductShell>
      <PageIntro
        eyebrow="Synthetic incidents"
        title="Simulations"
        description="Trigger a working disruption against an isolated airline world, then follow the real recovery run."
      />
      <SimulationsView />
    </ProductShell>
  );
}
