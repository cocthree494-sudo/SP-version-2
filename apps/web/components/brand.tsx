import Link from "next/link";

export function Brand({ href = "/" }: Readonly<{ href?: string }>) {
  return (
    <Link className="brand" href={href} aria-label="Relay support agent home">
      <span className="brand-mark" aria-hidden="true">
        <span />
        <span />
      </span>
      <span className="brand-word">Relay</span>
    </Link>
  );
}

