export default function DashboardLoading() {
  return (
    <div className="route-loading" aria-live="polite">
      <div className="skeleton skeleton-heading" />
      <div className="skeleton-grid">
        <div className="skeleton skeleton-card" />
        <div className="skeleton skeleton-card" />
      </div>
      <span className="sr-only">Loading dashboard</span>
    </div>
  );
}

