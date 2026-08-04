import Link from "next/link";

import { ArrowIcon, BookIcon, BotIcon, MessageIcon, SparkIcon } from "@/components/icons";

const steps = [
  {
    number: "01",
    title: "Create your first bot",
    body: "Give your support agent a name and a clear point of view.",
    icon: BotIcon,
    href: "/dashboard/bots",
  },
  {
    number: "02",
    title: "Add your knowledge",
    body: "Bring in the docs, answers, and policies your customers need.",
    icon: BookIcon,
    href: "/dashboard/knowledge",
  },
  {
    number: "03",
    title: "Meet it in the playground",
    body: "Ask a question and see a grounded answer before you go live.",
    icon: MessageIcon,
    href: null,
  },
];

export default function DashboardPage() {
  return (
    <div className="dashboard-page">
      <section className="welcome-hero" aria-labelledby="dashboard-title">
        <div className="hero-copy">
          <span className="eyebrow eyebrow-dark"><SparkIcon width={15} height={15} /> Your command center</span>
          <h1 id="dashboard-title">Make support feel <em>effortless.</em></h1>
          <p>One thoughtful workspace for the questions your customers ask most.</p>
          <Link className="button button-dark" href="/dashboard/bots">
            <span>Start with a bot</span>
            <ArrowIcon width={18} height={18} />
          </Link>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="hero-visual-grid" />
          <div className="hero-orbit orbit-a" />
          <div className="hero-orbit orbit-b" />
          <div className="hero-orbit orbit-c" />
          <div className="hero-spark spark-a">✦</div>
          <div className="hero-spark spark-b">✧</div>
          <div className="hero-signal-card">
            <span className="hero-signal-label">RELAY / SIGNAL 001</span>
            <div className="hero-signal-line"><span /><span /><span /><span /><span /><span /><span /></div>
            <strong>Ready when you are.</strong>
            <small>knowledge · context · care</small>
          </div>
        </div>
      </section>

      <section className="overview-section" aria-labelledby="setup-heading">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">The first three moves</span>
            <h2 id="setup-heading">Your workspace, in rhythm.</h2>
          </div>
          <span className="progress-label"><span>0</span> / 3 complete</span>
        </div>
        <div className="setup-progress" aria-label="0 of 3 setup steps complete"><span /></div>
        <div className="step-grid">
          {steps.map((step) => {
            const Icon = step.icon;
            return (
              <article className="step-card" key={step.number}>
                <div className="step-card-top">
                  <span className="step-number">{step.number}</span>
                  <span className="step-icon"><Icon width={20} height={20} /></span>
                </div>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
                {step.href ? (
                  <Link className="step-link step-link-active" href={step.href}>
                    Open workspace <ArrowIcon width={15} height={15} />
                  </Link>
                ) : (
                  <span className="step-link">Available in the next workspace update <ArrowIcon width={15} height={15} /></span>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <section className="quiet-note" aria-label="Workspace status">
        <span className="quiet-note-mark"><span /></span>
        <p><strong>Your foundation is live.</strong> Auth, tenant isolation, knowledge ingestion, and grounded routing are ready behind this shell.</p>
      </section>
    </div>
  );
}
