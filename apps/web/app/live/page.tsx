import type { Metadata } from "next";

import { FoundationState } from "@/components/foundation-state";
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
      <FoundationState
        index="01"
        title="Waiting for an authoritative world connection"
        description="PR1 does not invent network state. The live map and disruption facts will render only after the airline API and durable event stream are connected."
      />
    </ProductShell>
  );
}
