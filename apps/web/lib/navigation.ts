export const dashboardNavigation = [
  { label: "Live", href: "/live" },
  { label: "Runs", href: "/runs" },
  { label: "Data", href: "/data" },
  { label: "Simulations", href: "/simulations" },
] as const;

export const landingNavigation = [
  { label: "How it works", href: "/#how-it-works" },
  { label: "Scenarios", href: "/#scenarios" },
] as const;

export const dataSections = [
  "Flights",
  "Aircraft",
  "Crew",
  "Passengers",
  "Airports",
  "Disruptions",
] as const;

export const githubUrl =
  process.env.NEXT_PUBLIC_GITHUB_URL ??
  "https://github.com/PrathmeshAdsod/airstrong";
