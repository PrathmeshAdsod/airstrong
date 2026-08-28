import type { Metadata } from "next";

import { DataView } from "@/components/data-view";
import { PageIntro } from "@/components/page-intro";
import { ProductShell } from "@/components/product-shell";

export const metadata: Metadata = { title: "Data" };

export default function DataPage() {
  return (
    <ProductShell>
      <PageIntro
        eyebrow="Authoritative state"
        title="Data"
        description="The fictional operational world, exposed clearly and read directly from the airline service."
      />
      <DataView />
    </ProductShell>
  );
}
