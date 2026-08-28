import Link from "next/link";

type BrandProps = {
  compact?: boolean;
};

export function Brand({ compact = false }: BrandProps) {
  return (
    <Link className="brand" href="/" aria-label="Airstrong home">
      <svg
        aria-hidden="true"
        className="brand__mark"
        viewBox="0 0 38 38"
        fill="none"
      >
        <path d="M7 27.5 16.8 7h8.5L15.6 27.5H7Z" fill="currentColor" />
        <path
          d="m16.3 30.5 3.8-8h11.7l-3.9 8H16.3Z"
          fill="currentColor"
          opacity=".62"
        />
        <path
          d="m21.4 19.6 3.7-7.8 6.5 4.3-1.7 3.5h-8.5Z"
          fill="currentColor"
          opacity=".34"
        />
      </svg>
      {!compact && <span>Airstrong</span>}
    </Link>
  );
}
