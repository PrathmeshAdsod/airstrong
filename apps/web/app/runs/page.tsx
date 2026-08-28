import type { Metadata } from "next";

import { FoundationState } from "@/components/foundation-state";
import { PageIntro } from "@/components/page-intro";
import { ProductShell } from "@/components/product-shell";

export const metadata: Metadata = { title: "Runs" };

export default function RunsPage() {
  return (
    <ProductShell>
      <PageIntro
        eyebrow="Recovery record"
        title="Runs"
        description="A durable view of investigation, computation, validation, approval, execution, and verification."
      />
      <FoundationState
        index="02"
        title="No recovery run has been loaded"
        description="Run stages will be rendered from stored backend events. Refreshing this page will resume the same run instead of replaying progress."
      />
    </ProductShell>
  );
}
