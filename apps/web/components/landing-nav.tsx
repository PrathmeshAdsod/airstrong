import Link from "next/link";

import { githubUrl, landingNavigation } from "@/lib/navigation";

import { ArrowIcon } from "./arrow-icon";
import { Brand } from "./brand";

export function LandingNav() {
  return (
    <header className="landing-nav">
      <Brand />
      <nav aria-label="Landing page">
        {landingNavigation.map((item) => (
          <Link href={item.href} key={item.label}>
            {item.label}
          </Link>
        ))}
        <a href={githubUrl}>GitHub</a>
      </nav>
      <Link className="button button--primary button--nav" href="/live">
        Open Airstrong
        <span className="button__icon">
          <ArrowIcon />
        </span>
      </Link>
    </header>
  );
}
