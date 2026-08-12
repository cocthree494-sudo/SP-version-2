"use client";

import type {
  ProviderCatalogEntry,
  ProviderCredentialResponse,
  ProviderRoutingMode,
  GenerationProvider,
} from "@support-agent/api-client";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { PlusIcon, SearchIcon, TrashIcon } from "@/components/icons";
import { useAuth } from "@/lib/auth-context";
import { dashboardApi } from "@/lib/dashboard-api";

const MODE_COPY: Record<ProviderRoutingMode, { title: string; copy: string }> = {
  platform_only: {
    title: "Platform only",
    copy: "Use only the provider credentials managed by this platform.",
  },
  tenant_first_with_platform_fallback: {
    title: "Your key, then platform fallback",
    copy: "Try verified organization credentials first and explicitly fall back to the platform.",
  },
  tenant_only: {
    title: "Your key only",
    copy: "Never use platform generation credentials; fail safely when no verified key is active.",
  },
};

function dateText(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Not yet";
}

export function ProviderSettings() {
  const { user } = useAuth();
  const canManage = user?.role === "owner" || user?.role === "admin";
  const [credentials, setCredentials] = useState<ProviderCredentialResponse[]>([]);
  const [catalog, setCatalog] = useState<ProviderCatalogEntry[]>([]);
  const [mode, setMode] = useState<ProviderRoutingMode>("platform_only");
  const [credentialOrder, setCredentialOrder] = useState<string[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [selectedProviderId, setSelectedProviderId] = useState("openai");
  const [lowModel, setLowModel] = useState("gpt-4.1-mini");
  const [strongModel, setStrongModel] = useState("gpt-4.1");
  const [providerSearch, setProviderSearch] = useState("");
  const [rotating, setRotating] = useState<ProviderCredentialResponse | null>(null);
  const [rotateKey, setRotateKey] = useState("");
  const [revoking, setRevoking] = useState<ProviderCredentialResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const rotateInputRef = useRef<HTMLInputElement>(null);
  const keepCredentialRef = useRef<HTMLButtonElement>(null);

  const verified = useMemo(
    () => credentials.filter((item) => item.status === "verified" && item.revoked_at === null),
    [credentials],
  );
  const selectedProvider = useMemo(
    () => catalog.find((item) => item.id === selectedProviderId) ?? null,
    [catalog, selectedProviderId],
  );
  const filteredCatalog = useMemo(() => {
    const query = providerSearch.trim().toLowerCase();
    if (!query) return catalog;
    return catalog.filter((item) =>
      [item.label, item.id, ...item.aliases].some((value) => value.toLowerCase().includes(query)),
    );
  }, [catalog, providerSearch]);
  const catalogGroups = useMemo(() => {
    const groups = new Map<string, ProviderCatalogEntry[]>();
    filteredCatalog.forEach((item) => {
      const current = groups.get(item.setup_method) ?? [];
      current.push(item);
      groups.set(item.setup_method, current);
    });
    return groups;
  }, [filteredCatalog]);
  const catalogReadyCount = catalog.filter((item) => item.enabled).length;
  const catalogComingSoonCount = Math.max(catalog.length - catalogReadyCount, 0);

  useEffect(() => {
    if (!canManage) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    Promise.allSettled([
      dashboardApi.listProviderCatalog(),
      dashboardApi.listProviderCredentials(),
      dashboardApi.getProviderPolicy(),
    ])
      .then(([catalogResult, credentialsResult, policyResult]) => {
        if (cancelled) return;
        if (catalogResult.status === "fulfilled") setCatalog(catalogResult.value);
        if (credentialsResult.status === "fulfilled") setCredentials(credentialsResult.value);
        if (policyResult.status === "fulfilled") {
          setMode(policyResult.value.mode);
          setCredentialOrder(policyResult.value.credential_order);
        }
        const failures = [catalogResult, credentialsResult, policyResult]
          .filter((result): result is PromiseRejectedResult => result.status === "rejected");
        if (failures.length) {
          const first = failures[0].reason;
          setError(first instanceof Error ? first.message : "Some provider settings could not be loaded.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [canManage]);

  useEffect(() => {
    if (!selectedProvider) return;
    const firstModel = selectedProvider.models[0]?.id ?? "";
    const secondModel = selectedProvider.models[1]?.id ?? "";
    setLowModel((current) => selectedProvider.models.some((model) => model.id === current) ? current : firstModel);
    setStrongModel((current) => current && selectedProvider.models.some((model) => model.id === current) ? current : secondModel);
  }, [selectedProvider]);

  useEffect(() => {
    if (rotating) rotateInputRef.current?.focus();
  }, [rotating]);

  useEffect(() => {
    if (!providerSearch.trim() || !filteredCatalog.length) return;
    if (!filteredCatalog.some((item) => item.id === selectedProviderId)) {
      setSelectedProviderId(filteredCatalog[0].id);
    }
  }, [filteredCatalog, providerSearch, selectedProviderId]);

  function submitProviderSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (filteredCatalog[0]) setSelectedProviderId(filteredCatalog[0].id);
  }

  useEffect(() => {
    if (revoking) keepCredentialRef.current?.focus();
  }, [revoking]);

  function replaceCredential(updated: ProviderCredentialResponse) {
    setCredentials((current) => current.map((item) => item.id === updated.id ? updated : item));
  }

  async function addCredential(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canManage || saving || !selectedProvider?.enabled) return;
    const submittedKey = apiKey;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const created = await dashboardApi.createProviderCredential({
        provider: selectedProviderId as GenerationProvider,
        label: `${selectedProvider?.label ?? "Provider"} · ${lowModel}`,
        api_key: submittedKey,
        low_cost_model_id: lowModel.trim(),
        strong_model_id: strongModel.trim() || null,
      });
      setCredentials((current) => [...current, created]);
      setNotice("Credential encrypted and stored. Verify it before routing traffic.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The credential could not be added.");
    } finally {
      setApiKey("");
      setSaving(false);
    }
  }

  async function verifyCredential(credential: ProviderCredentialResponse) {
    setBusyId(credential.id);
    setError(null);
    setNotice(null);
    try {
      const updated = await dashboardApi.verifyProviderCredential(credential.id);
      replaceCredential(updated);
      setNotice(`${updated.label} verified successfully.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Credential verification failed.");
      const refreshed = await dashboardApi.listProviderCredentials().catch(() => null);
      if (refreshed) setCredentials(refreshed);
    } finally {
      setBusyId(null);
    }
  }

  async function rotateCredential(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!rotating || !rotateKey || saving) return;
    const target = rotating;
    const submittedKey = rotateKey;
    setSaving(true);
    setError(null);
    try {
      const updated = await dashboardApi.rotateProviderCredential(target.id, submittedKey);
      replaceCredential(updated);
      setCredentialOrder((current) => current.filter((id) => id !== target.id));
      setRotating(null);
      setNotice("Secret rotated. Verify the new key before adding it back to routing.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The credential could not be rotated.");
    } finally {
      setRotateKey("");
      setSaving(false);
    }
  }

  async function revokeCredential() {
    if (!revoking || saving) return;
    const target = revoking;
    setSaving(true);
    setError(null);
    try {
      await dashboardApi.revokeProviderCredential(target.id);
      setCredentials((current) => current.map((item) =>
        item.id === target.id
          ? { ...item, status: "revoked", revoked_at: new Date().toISOString() }
          : item,
      ));
      setCredentialOrder((current) => current.filter((id) => id !== target.id));
      setRevoking(null);
      setNotice("Credential revoked and removed from the next routing decision.");
    } catch (caught) {
      setRevoking(null);
      setError(caught instanceof Error ? caught.message : "The credential could not be revoked.");
    } finally {
      setSaving(false);
    }
  }

  function toggleCredential(id: string) {
    setCredentialOrder((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  function moveCredential(id: string, direction: -1 | 1) {
    setCredentialOrder((current) => {
      const index = current.indexOf(id);
      const target = index + direction;
      if (index === -1 || target < 0 || target >= current.length) return current;
      const copy = [...current];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      return copy;
    });
  }

  async function savePolicy() {
    if (!canManage || saving) return;
    const order = mode === "platform_only" ? [] : credentialOrder;
    if (mode !== "platform_only" && !order.length) {
      setError("Select at least one verified credential for tenant routing.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await dashboardApi.updateProviderPolicy(mode, order);
      setMode(updated.mode);
      setCredentialOrder(updated.credential_order);
      setNotice("Generation routing policy updated.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Routing policy could not be updated.");
    } finally {
      setSaving(false);
    }
  }

  if (!canManage) {
    return (
      <div className="workspace-screen">
        <header className="screen-heading"><div><span className="eyebrow">Provider custody</span><h1>Organization credentials.</h1><p>Only an owner or admin can inspect or change provider credentials and routing.</p></div></header>
        <div className="workspace-alert">Your member role does not have access to this security-sensitive workspace.</div>
      </div>
    );
  }

  return (
    <div className="workspace-screen provider-screen">
      <header className="screen-heading"><div><span className="eyebrow">Provider custody</span><h1>Bring your key. Keep routing explicit.</h1><p>Secrets are write-only, envelope encrypted, and never displayed again after submission.</p></div></header>
      {error ? <div className="workspace-alert workspace-alert-error" role="alert">{error}</div> : null}
      {notice ? <div className="workspace-alert workspace-alert-success" role="status">{notice}</div> : null}

      <section className="provider-catalog-panel" aria-labelledby="provider-catalog-title">
        <div className="provider-catalog-heading">
          <div><span className="eyebrow">Provider map</span><h2 id="provider-catalog-title">Every backend, one setup path.</h2><p>Choose a provider below. Ready adapters can be connected now; planned adapters stay visible so your workspace is ready for what comes next.</p></div>
          <div className="provider-catalog-counts" aria-label="Provider availability"><span><strong>{catalogReadyCount}</strong> ready</span><span><strong>{catalogComingSoonCount}</strong> coming soon</span></div>
        </div>
        <div className="provider-catalog-tools">
          <form className="provider-search-form" onSubmit={submitProviderSearch}>
          <label className="provider-search">Find a provider<input type="search" value={providerSearch} onChange={(event) => setProviderSearch(event.target.value)} placeholder="Search OpenAI, Gemini, Claude…" /></label>
            <button className="provider-search-button" type="submit" aria-label="Search providers" title="Search providers"><SearchIcon width={16} height={16} /></button>
          </form>
          <label className="provider-picker">Provider<select id="provider-picker" value={selectedProviderId} onChange={(event) => setSelectedProviderId(event.target.value)} disabled={loading || !catalog.length}>
            {[...catalogGroups.entries()].map(([method, entries]) => <optgroup label={method.replaceAll("_", " ")} key={method}>{entries.map((item) => <option value={item.id} disabled={!item.enabled} key={item.id}>{item.label}{item.enabled ? "" : " · coming soon"}</option>)}</optgroup>)}
          </select></label>
        </div>
        {selectedProvider && !selectedProvider.enabled ? <div className="provider-unavailable" role="status"><span className="provider-mark">{selectedProvider.label.slice(0, 2).toUpperCase()}</span><span><strong>{selectedProvider.label} is planned.</strong><small>{selectedProvider.availability_reason}</small></span></div> : null}
      </section>

      <div className="provider-layout">
        <div className="provider-stack">
          <section className="config-card">
            <div className="config-card-heading"><div><span className="eyebrow">Credentials</span><h2>Encrypted generation keys</h2></div></div>
            {loading ? <div className="skeleton provider-list-skeleton"/> : credentials.length ? (
              <div className="provider-list">
                {credentials.map((credential) => (
                  <article className="provider-row" key={credential.id}>
                    <div className="provider-row-main"><div><h3>{credential.label}</h3><span className={`state-badge state-${credential.status}`}><span/>{credential.status}</span></div><p>{credential.provider} · {credential.masked_secret}</p><dl><div><dt>Low-cost</dt><dd>{credential.low_cost_model_id}</dd></div><div><dt>Strong</dt><dd>{credential.strong_model_id ?? "Not configured"}</dd></div><div><dt>Verified</dt><dd>{dateText(credential.verified_at)}</dd></div></dl></div>
                    {credential.status !== "revoked" ? <div className="provider-actions"><button className="button button-quiet" type="button" onClick={() => void verifyCredential(credential)} disabled={busyId === credential.id}>{busyId === credential.id ? "Testing…" : "Test key"}</button><button className="button button-quiet" type="button" onClick={() => { setRotating(credential); setRotateKey(""); }}>Rotate</button><button className="icon-action icon-action-danger" type="button" aria-label={`Revoke ${credential.label}`} onClick={() => setRevoking(credential)}><TrashIcon width={15} height={15}/></button></div> : null}
                  </article>
                ))}
              </div>
            ) : <div className="source-empty"><p>No tenant generation credential has been added.</p></div>}
          </section>

          <section className="config-card">
            <div className="config-card-heading"><div><span className="eyebrow">Add key</span><h2>Write-only credential form</h2></div></div>
            <form className="workspace-form" onSubmit={addCredential} autoComplete="off">
              <div className="provider-selected-summary"><span className="provider-mark">{(selectedProvider?.label ?? "Provider").slice(0, 2).toUpperCase()}</span><span><strong>{selectedProvider?.label ?? "Choose a provider"}</strong><small>{selectedProvider?.enabled ? "API key setup · models are selected below" : "This adapter is not ready yet"}</small></span></div>
              <label>API key<input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} minLength={16} maxLength={2048} required autoComplete="new-password" spellCheck={false}/><small>Cleared from this form after every submission attempt. It is never stored in browser storage.</small></label>
              <div className="form-row"><label>Low-cost model<select value={lowModel} onChange={(event) => setLowModel(event.target.value)} required disabled={!selectedProvider?.enabled}>{selectedProvider?.models.map((model) => <option value={model.id} key={model.id}>{model.label} · {model.id}</option>)}</select></label><label>Strong model (optional)<select value={strongModel} onChange={(event) => setStrongModel(event.target.value)} disabled={!selectedProvider?.enabled}><option value="">No strong-model promotion</option>{selectedProvider?.models.map((model) => <option value={model.id} key={model.id}>{model.label} · {model.id}</option>)}</select></label></div>
              <div className="builder-submit"><button className="button button-primary" type="submit" disabled={saving || !apiKey || !selectedProvider?.enabled}><PlusIcon width={15} height={15}/> Encrypt and add</button></div>
            </form>
          </section>
        </div>

        <aside className="config-card policy-card">
          <div className="config-card-heading"><div><span className="eyebrow">Routing</span><h2>Generation policy</h2></div></div>
          <div className="policy-body">
            <div className="policy-modes">
              {(Object.keys(MODE_COPY) as ProviderRoutingMode[]).map((value) => <label className={mode === value ? "policy-mode policy-mode-active" : "policy-mode"} key={value}><input type="radio" name="routing-mode" value={value} checked={mode === value} onChange={() => setMode(value)}/><span><strong>{MODE_COPY[value].title}</strong><small>{MODE_COPY[value].copy}</small></span></label>)}
            </div>
            {mode !== "platform_only" ? <div className="policy-order"><h3>Verified credentials, in order</h3>{verified.length ? verified.map((credential) => { const selected = credentialOrder.includes(credential.id); const orderIndex = credentialOrder.indexOf(credential.id); return <div className={selected ? "policy-credential policy-credential-selected" : "policy-credential"} key={credential.id}><label><input type="checkbox" checked={selected} onChange={() => toggleCredential(credential.id)}/><span><strong>{credential.label}</strong><small>{credential.masked_secret}</small></span></label>{selected ? <span className="order-actions"><button type="button" aria-label={`Move ${credential.label} up`} onClick={() => moveCredential(credential.id, -1)} disabled={orderIndex === 0}>↑</button><button type="button" aria-label={`Move ${credential.label} down`} onClick={() => moveCredential(credential.id, 1)} disabled={orderIndex === credentialOrder.length - 1}>↓</button></span> : null}</div>; }) : <p>Verify a credential before selecting tenant routing.</p>}</div> : null}
            <button className="button button-dark policy-save" type="button" onClick={() => void savePolicy()} disabled={saving}>{saving ? "Saving…" : "Save routing policy"}</button>
            <p className="policy-warning">Embedding remains platform-managed. Arbitrary provider URLs are not accepted.</p>
          </div>
        </aside>
      </div>

      {rotating ? <div className="dialog-backdrop" role="presentation"><section className="workspace-dialog" role="dialog" aria-modal="true" aria-labelledby="rotate-title"><div className="dialog-heading"><div><span className="eyebrow">Rotate secret</span><h2 id="rotate-title">Replace {rotating.label}</h2></div><button className="dialog-close" type="button" onClick={() => { setRotating(null); setRotateKey(""); }} disabled={saving}>×</button></div><form className="workspace-form" onSubmit={rotateCredential} autoComplete="off"><label>New API key<input ref={rotateInputRef} type="password" value={rotateKey} onChange={(event) => setRotateKey(event.target.value)} minLength={16} maxLength={2048} required autoComplete="new-password" spellCheck={false}/></label><p className="form-note">Rotation marks this credential unverified and removes it from usable routing until tested again.</p><div className="dialog-actions"><button className="button button-quiet" type="button" onClick={() => { setRotating(null); setRotateKey(""); }} disabled={saving}>Cancel</button><button className="button button-primary" type="submit" disabled={saving || !rotateKey}>{saving ? "Rotating…" : "Rotate key"}</button></div></form></section></div> : null}

      {revoking ? <div className="dialog-backdrop" role="presentation"><section className="workspace-dialog workspace-dialog-small" role="alertdialog" aria-modal="true" aria-labelledby="revoke-provider-title"><span className="danger-icon"><TrashIcon width={21} height={21}/></span><h2 id="revoke-provider-title">Revoke {revoking.label}?</h2><p>The next routing decision will stop using this credential. This action cannot be reversed.</p><div className="dialog-actions"><button ref={keepCredentialRef} className="button button-quiet" type="button" onClick={() => setRevoking(null)} disabled={saving}>Keep credential</button><button className="button button-danger" type="button" onClick={() => void revokeCredential()} disabled={saving}>{saving ? "Revoking…" : "Revoke credential"}</button></div></section></div> : null}
    </div>
  );
}
