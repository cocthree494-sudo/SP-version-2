import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function IconFrame({ children, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {children}
    </svg>
  );
}

export function ArrowIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </IconFrame>
  );
}

export function BotIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <rect x="4" y="7" width="16" height="12" rx="4" />
      <path d="M12 3v4M8.5 12h.01M15.5 12h.01M9 16h6" />
    </IconFrame>
  );
}

export function BookIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22V5.5ZM20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22V5.5Z" />
    </IconFrame>
  );
}

export function GridIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <rect x="3" y="3" width="7" height="7" rx="2" />
      <rect x="14" y="3" width="7" height="7" rx="2" />
      <rect x="3" y="14" width="7" height="7" rx="2" />
      <rect x="14" y="14" width="7" height="7" rx="2" />
    </IconFrame>
  );
}

export function MessageIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M21 11.5a8.4 8.4 0 0 1-9 8.5 9.6 9.6 0 0 1-4-.9L3 21l1.8-4.4A8.7 8.7 0 1 1 21 11.5Z" />
    </IconFrame>
  );
}

export function SparkIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="m12 3 1.25 4.25L17.5 8.5l-4.25 1.25L12 14l-1.25-4.25L6.5 8.5l4.25-1.25L12 3Z" />
      <path d="m19 15 .6 2.4L22 18l-2.4.6L19 21l-.6-2.4L16 18l2.4-.6L19 15Z" />
    </IconFrame>
  );
}

export function UserIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4.5 21a7.5 7.5 0 0 1 15 0" />
    </IconFrame>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M12 5v14M5 12h14" />
    </IconFrame>
  );
}

export function EditIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="m4 16-.8 4.8L8 20l11-11-4-4L4 16Z" />
      <path d="m13.5 6.5 4 4" />
    </IconFrame>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6" />
    </IconFrame>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M12 16V4M7 9l5-5 5 5M5 14v6h14v-6" />
    </IconFrame>
  );
}

export function GlobeIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
    </IconFrame>
  );
}

export function PhoneIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M6.6 3.5 9 3l2 4-2.2 1.8a14.4 14.4 0 0 0 6.4 6.4L17 13l4 2-.5 2.4a3 3 0 0 1-3.2 2.4C10.8 19.1 4.9 13.2 4.2 6.7a3 3 0 0 1 2.4-3.2Z" />
    </IconFrame>
  );
}

export function SearchIcon(props: IconProps) {
  return <IconFrame {...props}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 5 5" /></IconFrame>;
}

export function GoogleIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" {...props}>
      <path fill="#4285F4" d="M21.35 12.1c0-.74-.07-1.46-.21-2.15H12v4.07h5.24a4.48 4.48 0 0 1-1.94 2.94v2.45h3.14c1.84-1.7 2.91-4.2 2.91-7.31Z" />
      <path fill="#34A853" d="M12 21.5c2.63 0 4.84-.87 6.45-2.36l-3.14-2.45c-.87.58-1.98.92-3.31.92-2.54 0-4.69-1.72-5.46-4.03H3.3v2.53A9.74 9.74 0 0 0 12 21.5Z" />
      <path fill="#FBBC05" d="M6.54 13.58a5.85 5.85 0 0 1 0-3.16V7.89H3.3a9.76 9.76 0 0 0 0 8.22l3.24-2.53Z" />
      <path fill="#EA4335" d="M12 6.39c1.43 0 2.71.49 3.72 1.45l2.79-2.79C16.84 3.51 14.63 2.5 12 2.5a9.74 9.74 0 0 0-8.7 5.39l3.24 2.53C7.31 8.11 9.46 6.39 12 6.39Z" />
    </svg>
  );
}

export function MicrosoftIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" {...props}>
      <path fill="#F25022" d="M2.5 2.5h9.1v9.1H2.5z" />
      <path fill="#7FBA00" d="M12.4 2.5h9.1v9.1h-9.1z" />
      <path fill="#00A4EF" d="M2.5 12.4h9.1v9.1H2.5z" />
      <path fill="#FFB900" d="M12.4 12.4h9.1v9.1h-9.1z" />
    </svg>
  );
}

export function GitHubIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" {...props}>
      <path fill="currentColor" d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2.18c-3.2.7-3.87-1.36-3.87-1.36-.53-1.34-1.3-1.7-1.3-1.7-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.02 1.75 2.67 1.24 3.32.95.1-.74.4-1.24.73-1.52-2.55-.29-5.23-1.28-5.23-5.7 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.47.11-3.06 0 0 .97-.31 3.16 1.18a10.95 10.95 0 0 1 5.76 0c2.2-1.49 3.16-1.18 3.16-1.18.62 1.59.23 2.77.11 3.06.73.81 1.18 1.84 1.18 3.1 0 4.43-2.68 5.41-5.24 5.7.41.36.78 1.07.78 2.16v3.2c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5Z" />
    </svg>
  );
}
