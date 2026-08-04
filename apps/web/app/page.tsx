import Link from "next/link";

import { Brand } from "@/components/brand";
import { ArrowIcon } from "@/components/icons";

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
      <section className="landing-footer-note"><span>01</span><p>Knowledge in. Signal out.</p><span>↓</span></section>
    </main>
  );
}
