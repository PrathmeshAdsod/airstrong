import type { Metadata } from "next";

import { FoundationState } from "@/components/foundation-state";
import { PageIntro } from "@/components/page-intro";
import { ProductShell } from "@/components/product-shell";

export const metadata: Metadata = { title: "Simulations" };

export default function SimulationsPage() {
  return (
    <ProductShell>
      <PageIntro
        eyebrow="Synthetic incidents"
        title="Simulations"
        description="Trigger a working disruption against an isolated airline world, then follow the real recovery run."
      />
      <FoundationState
        index="04"
        title="No scenario is published before it works"
        description="The cyclone and unavailable-aircraft hero will appear here only after its mutation, recovery, approval, execution, reconnect, and verification path passes end to end."
      />
    </ProductShell>
  );
}
