import Link from "next/link";

import { Brand } from "@/components/brand";
import { ArrowIcon, BookIcon, BotIcon, MessageIcon, PhoneIcon } from "@/components/icons";

export default function HomePage() {
  return (
    <main className="landing-page">
      <nav className="landing-nav" aria-label="Main navigation">
        <Brand />
        <div className="landing-nav-actions">
          <Link className="text-link" href="/login">Sign in</Link>
          <Link className="button button-small button-dark" href="/register">Start building <ArrowIcon width={16} height={16} /></Link>
        </div>
      </nav>
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-copy">
          <span className="eyebrow eyebrow-dark"><span className="eyebrow-pulse" /> Customer support, in sync</span>
          <h1 id="landing-title">The clear signal in every customer conversation.</h1>
          <p>Relay turns your team&apos;s knowledge into grounded, multilingual support that feels unmistakably human.</p>
          <div className="landing-actions">
            <Link className="button button-dark" href="/register">Create your workspace <ArrowIcon width={18} height={18} /></Link>
            <Link className="text-link text-link-arrow" href="/login">I already have an account <ArrowIcon width={16} height={16} /></Link>
          </div>
          <div className="landing-proof"><span className="proof-avatars"><i>AR</i><i>NL</i><i>KM</i></span><span>Built for teams who care about the answer.</span></div>
        </div>
        <div className="landing-art" aria-hidden="true">
          <div className="landing-art-noise" />
          <div className="landing-ring ring-one" />
          <div className="landing-ring ring-two" />
          <div className="landing-ring ring-three" />
          <div className="landing-art-core"><span className="core-line" /><span className="core-line" /><span className="core-line" /></div>
          <span className="art-label art-label-top">GROUND / 01</span>
          <span className="art-label art-label-bottom">QUALITY OVER NOISE</span>
          <span className="art-star art-star-one">✦</span>
          <span className="art-star art-star-two">✧</span>
        </div>
      </section>
      <section className="landing-capabilities" aria-labelledby="capabilities-title">
        <div className="landing-section-heading">
          <span className="eyebrow">One support loop</span>
          <h2 id="capabilities-title">From trusted source to customer-ready answer.</h2>
          <p>Relay keeps the knowledge, agent, channel, and safety decisions behind every answer in one workspace.</p>
        </div>
        <div className="landing-capability-grid">
          <article><BookIcon width={21} height={21} /><strong>Trusted knowledge</strong><span>Ground answers in approved files, websites, and maintained Q&amp;A.</span></article>
          <article><BotIcon width={21} height={21} /><strong>Purpose-built agents</strong><span>Give each support agent its own instructions, model route, and publishing state.</span></article>
          <article><MessageIcon width={21} height={21} /><strong>Connected channels</strong><span>Serve web, Telegram, WhatsApp Business, Facebook Page, and email workflows.</span></article>
          <article><PhoneIcon width={21} height={21} /><strong>Controlled voice</strong><span>Keep outbound calls, recording consent, interruptions, and cost boundaries explicit.</span></article>
        </div>
      </section>
      <section className="landing-trace" aria-labelledby="trace-title">
        <div className="landing-trace-copy">
          <span className="eyebrow eyebrow-light">Answer trace</span>
          <h2 id="trace-title">Helpful does not have to mean unaccountable.</h2>
          <p>Support teams can see what the agent answered, which source grounded it, and which channel carried it.</p>
          <Link className="text-link text-link-arrow" href="/docs">Explore the documentation <ArrowIcon width={16} height={16} /></Link>
        </div>
        <div className="landing-answer-preview" aria-label="Example grounded support answer">
          <div className="answer-preview-head"><span>Voice support · policy question</span><strong>Grounded</strong></div>
          <p className="answer-preview-question">Does call recording start automatically?</p>
          <p className="answer-preview-response">No. Recording is off by default and requires separate consent before it can be enabled.</p>
          <div className="answer-preview-source"><BookIcon width={15} height={15} /><span>Source: Voice call agent · Guide 07</span></div>
        </div>
      </section>
      <footer className="landing-site-footer">
        <Brand />
        <p>Knowledge in. Signal out.</p>
        <nav aria-label="Footer navigation">
          <Link href="/docs">Documentation</Link>
          <Link href="/login">Sign in</Link>
          <Link href="/register">Create workspace</Link>
        </nav>
      </footer>
    </main>
  );
}
