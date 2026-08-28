import type { Metadata } from "next";

import { PageIntro } from "@/components/page-intro";
import { ProductShell } from "@/components/product-shell";
import { RunsView } from "@/components/runs-view";

export const metadata: Metadata = { title: "Runs" };

export default function RunsPage() {
  return (
    <ProductShell>
      <PageIntro
        eyebrow="Recovery record"
        title="Runs"
        description="A durable view of investigation, computation, validation, approval, execution, and verification."
      />
      <RunsView />
    </ProductShell>
  );
}
