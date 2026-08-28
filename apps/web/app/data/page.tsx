import type { Metadata } from "next";

import { FoundationState } from "@/components/foundation-state";
import { PageIntro } from "@/components/page-intro";
import { ProductShell } from "@/components/product-shell";
import { dataSections } from "@/lib/navigation";

export const metadata: Metadata = { title: "Data" };

export default function DataPage() {
  return (
    <ProductShell>
      <PageIntro
        eyebrow="Authoritative state"
        title="Data"
        description="The fictional operational world, exposed clearly and read directly from the airline service."
      />
      <ul className="data-section-list" aria-label="Operational data sections">
        {dataSections.map((section, index) => (
          <li key={section} className={index === 0 ? "is-selected" : undefined}>
            {section}
          </li>
        ))}
      </ul>
      <FoundationState
        index="03"
        title="No authoritative rows are connected"
        description="Flights, aircraft, crew, passengers, airports, and disruptions will share one backend state. Scenario mutations, approved writes, and reset will change these views together."
      />
    </ProductShell>
  );
}
