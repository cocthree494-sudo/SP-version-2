"use client";

export default function DashboardError({ reset }: Readonly<{ reset: () => void }>) {
  return (
    <div className="route-error" role="alert">
      <span className="eyebrow">A small detour</span>
      <h1>We couldn&apos;t load this view.</h1>
      <p>Try the request again. Your workspace data is safe.</p>
      <button className="button button-dark" type="button" onClick={reset}>Try again</button>
    </div>
  );
}

