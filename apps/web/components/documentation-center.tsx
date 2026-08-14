"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Brand } from "@/components/brand";
import { BookIcon, SearchIcon } from "@/components/icons";
import { documentationSections } from "@/lib/docs-content";

export function DocumentationCenter({ publicPage = false }: Readonly<{ publicPage?: boolean }>) {
  const [query, setQuery] = useState("");
  const normalized = query.trim().toLowerCase();
  const results = useMemo(() => documentationSections.filter((section) => {
    if (!normalized) return true;
    return [section.title, section.summary, ...section.topics, ...section.steps].join(" ").toLowerCase().includes(normalized);
  }), [normalized]);

  return (
    <div className={`documentation-page ${publicPage ? "documentation-public" : "dashboard-page"}`}>
      {publicPage ? (
        <nav className="documentation-public-nav" aria-label="Public documentation navigation">
          <Brand />
          <div>
            <Link className="text-link" href="/login">Sign in</Link>
            <Link className="button button-small button-dark" href="/register">Start building</Link>
          </div>
        </nav>
      ) : null}
      <section className="documentation-hero">
        <div>
          <span className="eyebrow"><BookIcon width={14} height={14} />Relay documentation</span>
          <h1>Answers before you need to ask.</h1>
          <p>Practical guidance for setting up your workspace, protecting connected accounts, and shipping helpful support experiences.</p>
        </div>
        <div className="documentation-search">
          <label htmlFor="documentation-search">
            <span className="sr-only">Search documentation</span>
            <SearchIcon width={17} height={17} />
            <input id="documentation-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search setup, channels, providers…" />
          </label>
          <span>{results.length} of {documentationSections.length} guides</span>
        </div>
      </section>
      <div className="documentation-layout">
        <nav className="documentation-index" aria-label="Documentation sections">
          <strong>On this page</strong>
          {results.map((section) => <a href={`#${section.id}`} key={section.id}>{section.title}</a>)}
        </nav>
        <main className="documentation-list">
          {results.length === 0 ? (
            <div className="empty-state"><strong>No matching guide.</strong><span>Try a provider, channel, security, or voice search.</span></div>
          ) : results.map((section) => (
            <article className="documentation-card" id={section.id} key={section.id}>
              <span className="eyebrow">Guide {String(documentationSections.indexOf(section) + 1).padStart(2, "0")}</span>
              <h2>{section.title}</h2>
              <p>{section.summary}</p>
              <ol>{section.steps.map((step) => <li key={step}>{step}</li>)}</ol>
            </article>
          ))}
        </main>
      </div>
      {publicPage ? (
        <div className="documentation-footer">
          <Link className="button button-dark" href="/login">Open your workspace</Link>
          <span>Documentation is updated alongside the product release.</span>
        </div>
      ) : null}
    </div>
  );
}
