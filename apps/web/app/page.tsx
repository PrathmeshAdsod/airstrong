import Link from "next/link";

import { ArrowIcon } from "@/components/arrow-icon";
import { LandingNav } from "@/components/landing-nav";
import { githubUrl } from "@/lib/navigation";

const workflow = [
  {
    number: "01",
    title: "See the incident",
    copy: "Read the current operation and follow its aircraft, crew, and passenger dependencies.",
  },
  {
    number: "02",
    title: "Build the problem",
    copy: "Generate scenario-specific computation from the facts found by three domain investigators.",
  },
  {
    number: "03",
    title: "Test each candidate",
    copy: "Run candidate actions in a sandbox, then let the operational twin enforce the hard rules.",
  },
  {
    number: "04",
    title: "Ask, act, verify",
    copy: "Pause for approval, apply idempotent writes, and re-read the world before calling it stable.",
  },
] as const;

const runStages = [
  ["State", "World snapshot stored"],
  ["Investigate", "Three reports received"],
  ["Compute", "Generated code in sandbox"],
  ["Validate", "Twin decides what is valid"],
  ["Approve", "No write before a person agrees"],
] as const;

export default function LandingPage() {
  return (
    <div className="landing-page">
      <LandingNav />

      <main>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero__copy">
            <p className="signal-label">
              <span aria-hidden="true">✦</span>
              Recovery decisions, checked before they move
            </p>
            <h1 id="hero-title">
              When operations change,
              <span> test the next move.</span>
            </h1>
            <p className="hero__lede">
              Airstrong checks the disruption, computes recovery candidates,
              tests them against an operational twin, and asks before changing
              the airline.
            </p>
            <div className="hero__actions">
              <Link className="button button--primary" href="/live">
                Open Airstrong
                <span className="button__icon">
                  <ArrowIcon />
                </span>
              </Link>
              <Link className="text-link" href="/#how-it-works">
                See how it works
                <ArrowIcon />
              </Link>
            </div>
          </div>

          <aside className="run-thread" aria-label="Recovery run sequence">
            <div className="run-thread__heading">
              <div>
                <p>One run, fully traced</p>
                <h2>Facts before action</h2>
              </div>
              <span className="run-thread__live">
                <span aria-hidden="true" />
                Durable state
              </span>
            </div>
            <ol>
              {runStages.map(([stage, result], index) => (
                <li key={stage}>
                  <span className="run-thread__number">{index + 1}</span>
                  <span className="run-thread__stage">{stage}</span>
                  <strong>{result}</strong>
                </li>
              ))}
            </ol>
            <p className="run-thread__note">
              Status comes from stored events, never from a browser timer.
            </p>
          </aside>
        </section>

        <section
          className="workflow"
          id="how-it-works"
          aria-labelledby="workflow-title"
        >
          <div className="section-heading">
            <p className="eyebrow">How it works</p>
            <h2 id="workflow-title">One incident. Four clear decisions.</h2>
            <p>
              Agents decide what to inspect and compute. Deterministic software
              decides what is valid and what ranks first.
            </p>
          </div>
          <ol className="workflow__steps">
            {workflow.map((step) => (
              <li key={step.number}>
                <span>{step.number}</span>
                <h3>{step.title}</h3>
                <p>{step.copy}</p>
              </li>
            ))}
          </ol>
        </section>

        <section
          className="scenario-story"
          id="scenarios"
          aria-labelledby="scenario-title"
        >
          <div className="scenario-story__copy">
            <p className="eyebrow">Hero incident</p>
            <h2 id="scenario-title">
              A cyclone closes capacity. One aircraft is unavailable.
            </h2>
            <p>
              The baseline is designed to create real downstream pressure at
              BOM. Airstrong must discover the affected rotations, duties, and
              connections from the stored world. The winning candidate is not
              known in advance.
            </p>
          </div>
          <div
            className="scenario-story__rules"
            aria-label="Scenario guarantees"
          >
            <div>
              <span>01</span>
              <strong>No seeded outcome</strong>
            </div>
            <div>
              <span>02</span>
              <strong>Twin owns validity</strong>
            </div>
            <div>
              <span>03</span>
              <strong>Approval owns writes</strong>
            </div>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <p>Airstrong</p>
        <span>Synthetic airline. Real recovery workflow.</span>
        <a href={githubUrl}>GitHub</a>
      </footer>
    </div>
  );
}
