"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { C, SCREEN_NAMES, SCREEN_DESC, REASON_EXPLAIN, CLOUDLY_SUGGESTIONS } from "@/lib/constants";
import { fmt, monthLabel, shortMonth } from "@/lib/utils";
import {
  FadeIn, Stagger, Card, CardLabel, CardSub, BigNum, Change,
  Skeleton, SkeletonScreen, ErrorState, ReasonBadge, useToast,
} from "@/components/ui";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

/* ═══ Top navigation ════════════════════════════════════════════════════════ */

function TopNav({ screen, onNav, pipelineDone, onCloudly }: { screen: number; onNav: (s: number) => void; pipelineDone: boolean; onCloudly?: () => void }) {
  const tabs = pipelineDone
    ? [
        { idx: 0, label: "Upload" },
        { idx: 1, label: "Overview" },
        { idx: 2, label: "Ingestion" },
        { idx: 3, label: "Variance" },
        { idx: 4, label: "Root Causes" },
        { idx: 5, label: "Close Packet" },
        { idx: 6, label: "Engineering" },
        { idx: 7, label: "Trends" },
      ]
    : [];

  return (
    <div
      className="cl-nav flex items-center gap-1 px-6 py-3 mb-6 rounded-2xl"
      style={{ background: C.card, border: `1px solid ${C.border}`, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}
    >
      {/* Logo — click to go home */}
      <button
        onClick={() => onNav(-1)}
        className="flex items-center gap-2 mr-6 cursor-pointer"
        style={{ background: "none", border: "none" }}
      >
        <svg width="20" height="16" viewBox="0 0 120 85" fill="none">
          <path
            d="M30 65C18 65 10 57 10 47c0-9 6-16 14-18 0-14 12-24 26-24 11 0 20 6 24 15 2-1 5-2 8-2 10 0 18 8 18 18h2c8 0 14 6 14 14s-6 14-14 14H30z"
            stroke={C.accent}
            strokeWidth="4"
            fill="none"
          />
        </svg>
        <span className="text-sm font-semibold" style={{ color: C.accent }}>CloudLedger</span>
      </button>

      {/* Tabs */}
      {tabs.map(({ idx, label }) => {
        const active = idx === screen;
        return (
          <button
            key={idx}
            onClick={() => onNav(idx)}
            data-active={active}
            title={`${label} (${idx + 1})`}
            className="cl-tab px-4 py-1.5 rounded-full text-[13px] font-medium cursor-pointer"
            style={{
              background: active ? C.accent : "transparent",
              color: active ? "#FFFFFF" : C.text,
            }}
          >
            {label}
          </button>
        );
      })}

      {/* Ask Cloudly button */}
      <div className="ml-auto">
        {pipelineDone && onCloudly && (
          <button onClick={onCloudly}
            className="cl-btn flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[12px] font-medium cursor-pointer"
            style={{ background: "rgba(201,99,58,0.1)", color: C.accent, border: `1px solid rgba(201,99,58,0.2)` }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a7 7 0 0 1 7 7c0 2.4-1.2 4.5-3 5.7V17a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2v-2.3C6.2 13.5 5 11.4 5 9a7 7 0 0 1 7-7z"/>
              <line x1="10" y1="22" x2="14" y2="22"/>
            </svg>
            Ask Cloudly
          </button>
        )}
      </div>
    </div>
  );
}

/* ═══ Landing Page ══════════════════════════════════════════════════════════ */

function LandingPage({ onStart }: { onStart: () => void }) {
  return (
    <div>
      {/* Hero */}
      <div className="text-center py-20">
        <p className="text-xs font-medium tracking-widest uppercase mb-4" style={{ color: C.accent, letterSpacing: "0.15em" }}>
          Cloud Variance Analysis
        </p>
        <h1 className="text-5xl font-semibold leading-[1.1] tracking-tight mb-5" style={{ color: C.text }}>
          Close your cloud month<br />in 5 minutes.
        </h1>
        <p className="text-base max-w-xl mx-auto mb-10 leading-relaxed" style={{ color: C.muted }}>
          Trace every dollar of cloud variance to a specific engineering decision.
          Upload billing data and Terraform state. Get a CFO-ready close packet in minutes.
        </p>
        <button
          onClick={onStart}
          className="cl-btn px-8 py-3.5 rounded-xl text-sm font-semibold cursor-pointer"
          style={{ background: C.accent, color: "#FFFFFF", border: "none" }}
        >
          Start analysis
        </button>
      </div>

      {/* Problem statement */}
      <Card className="mb-6">
        <CardLabel>The month-end close problem</CardLabel>
        <p className="text-sm mt-2 leading-relaxed" style={{ color: C.text }}>
          Every month, finance controllers get a cloud bill that&apos;s different from last month.
          Nobody can explain why. Engineering shipped a dozen changes, but nobody tracks which change
          cost what. The controller spends three days manually reconciling spreadsheets to close the books.
          CloudLedger automates that reconciliation.
        </p>
      </Card>

      {/* How it works */}
      <CardLabel>How it works</CardLabel>
      <div className="grid grid-cols-3 gap-4 mt-2 mb-6">
        <Card>
          <p className="text-sm font-semibold mb-2" style={{ color: C.accent }}>1. Upload your billing export</p>
          <p className="text-xs leading-relaxed" style={{ color: C.text }}>
            CloudLedger accepts AWS FOCUS 1.2 exports — the industry-standard format AWS already produces.
            Two months of data is enough to start.
          </p>
        </Card>
        <Card>
          <p className="text-sm font-semibold mb-2" style={{ color: C.accent }}>2. Connect your infrastructure code</p>
          <p className="text-xs leading-relaxed" style={{ color: C.text }}>
            Upload your Terraform state file. CloudLedger joins every billed resource against your
            infrastructure code to identify what was approved versus what appeared without review.
          </p>
        </Card>
        <Card>
          <p className="text-sm font-semibold mb-2" style={{ color: C.accent }}>3. Get a close packet in five minutes</p>
          <p className="text-xs leading-relaxed" style={{ color: C.text }}>
            Every dollar of variance is assigned a reason code. Drift is flagged for engineering.
            Approved changes are traced to pull requests. The close packet exports as PDF or CSV.
          </p>
        </Card>
      </div>

      {/* What you get */}
      <Card className="mb-6">
        <CardLabel>What the close packet contains</CardLabel>
        <ul className="mt-2 space-y-1.5 text-sm" style={{ color: C.text }}>
          {[
            "Invoice reconciliation tied to the billed total with audit trail",
            "Variance broken down by service and by reason code",
            "Every cost change linked to either a Terraform change or a drift event",
            "Journal entry CSV ready for QuickBooks or NetSuite import",
            "Executive summary PDF for CFO review",
          ].map((item) => (
            <li key={item} className="flex gap-2">
              <span style={{ color: C.accent }}>&#8226;</span>
              {item}
            </li>
          ))}
        </ul>
      </Card>

      {/* Who uses it */}
      <CardLabel>Built for two roles</CardLabel>
      <div className="grid grid-cols-2 gap-4 mt-2 mb-6">
        <Card>
          <p className="text-sm font-semibold mb-2" style={{ color: C.accent }}>Finance controllers</p>
          <p className="text-xs leading-relaxed" style={{ color: C.text }}>
            You close the books every month. You need to explain the cloud bill variance to your CFO
            without spending three days on it. CloudLedger produces the explanation automatically.
          </p>
        </Card>
        <Card>
          <p className="text-sm font-semibold mb-2" style={{ color: C.accent }}>Platform engineers</p>
          <p className="text-xs leading-relaxed" style={{ color: C.text }}>
            You ship infrastructure changes every week. You want to see which of your decisions moved
            the bill, and you need visibility into drift before finance brings it up. CloudLedger gives you both.
          </p>
        </Card>
      </div>

      {/* Footer */}
      <div className="text-center py-8" style={{ borderTop: `1px solid ${C.border}` }}>
        <p className="text-xs mb-6" style={{ color: C.muted }}>
          CloudLedger &middot; AWS FOCUS 1.2 compatible &middot; Built for the month-end close
        </p>
        <button
          onClick={onStart}
          className="cl-btn px-8 py-3 rounded-lg text-sm font-semibold cursor-pointer"
          style={{ background: C.accent, color: "#FFFFFF", border: "none" }}
        >
          Start your analysis
        </button>
      </div>
    </div>
  );
}

/* ═══ File upload slot ══════════════════════════════════════════════════════ */

function FileSlot({ label, sub, accept, file, onFile }: {
  label: string; sub: string; accept: string; file: File | null; onFile: (f: File | null) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <Card>
      <CardLabel>{label}</CardLabel>
      <CardSub>{sub}</CardSub>
      <input ref={ref} type="file" accept={accept} className="hidden"
        onChange={e => onFile(e.target.files?.[0] || null)} />
      <button
        onClick={() => ref.current?.click()}
        className="w-full mt-3 py-4 rounded-lg text-xs font-medium cursor-pointer"
        style={{
          border: `1.5px dashed ${file ? C.accent : C.border}`,
          color: file ? C.accent : C.muted,
          background: file ? "rgba(201,99,58,0.04)" : "transparent",
        }}
      >
        {file ? file.name : "Choose file or drag & drop"}
      </button>
      {file && (
        <button
          onClick={() => { onFile(null); if (ref.current) ref.current.value = ""; }}
          className="text-[11px] mt-1 cursor-pointer"
          style={{ color: C.muted, background: "none", border: "none", textDecoration: "underline" }}
        >
          Remove
        </button>
      )}
    </Card>
  );
}

/* ═══ Screen 0: Upload ══════════════════════════════════════════════════════ */

interface UploadFiles {
  billingFiles: File[];
  terraform: File | null;
}

function UploadScreen({ files, setFiles, onDone }: {
  files: UploadFiles;
  setFiles: (f: UploadFiles) => void;
  onDone: (p: string, c: string, all: string[]) => void;
}) {
  const [running, setRunning] = useState(false);
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [uploadMode, setUploadMode] = useState<"files" | "aws" | "azure">("files");
  const [cloudCreds, setCloudCreds] = useState<Record<string, string>>({});
  const [cloudMonths, setCloudMonths] = useState(2);
  const billingRef = useRef<HTMLInputElement>(null);

  const ready = files.billingFiles.length >= 2 && files.terraform;
  const steps = ["Uploading billing CSVs...", "Uploading Terraform state...", "Detecting billing periods...", "Running variance analysis..."];

  async function run() {
    if (files.billingFiles.length < 2 || !files.terraform) return;
    setRunning(true);
    setError(null);
    try {
      setStep(1);
      await api.uploadCSV(files.billingFiles);
      setStep(2);
      await api.uploadTerraform([files.terraform]);
      setStep(3);
      const { periods } = await api.getPeriods();
      if (periods.length < 2) {
        setError("Could not detect two billing periods from the uploaded files. Check the BillingPeriodStart column.");
        setRunning(false);
        setStep(0);
        return;
      }
      setStep(4);
      // Run variance for all consecutive period pairs
      if (periods.length > 2) {
        await api.runPipelineAll();
      } else {
        await api.runPipeline(periods[1], periods[0]);
      }
      onDone(periods[periods.length - 1], periods[periods.length - 2], periods);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Pipeline failed");
      setRunning(false);
      setStep(0);
    }
  }

  async function runCloud() {
    setRunning(true);
    setError(null);
    try {
      setStep(1);
      if (uploadMode === "aws") {
        await api.connectAWS(cloudCreds.accessKey || "", cloudCreds.secretKey || "", cloudCreds.region || "us-east-1", cloudMonths);
      } else {
        await api.connectAzure(cloudCreds.subscriptionId || "", cloudCreds.tenantId || "", cloudCreds.clientId || "", cloudCreds.clientSecret || "", cloudMonths);
      }
      setStep(2);
      if (files.terraform) {
        await api.uploadTerraform([files.terraform]);
      }
      setStep(3);
      const { periods } = await api.getPeriods();
      if (periods.length < 2) { setError("Could not detect billing periods."); setRunning(false); setStep(0); return; }
      setStep(4);
      if (periods.length > 2) { await api.runPipelineAll(); } else { await api.runPipeline(periods[1], periods[0]); }
      onDone(periods[periods.length - 1], periods[periods.length - 2], periods);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Connection failed");
      setRunning(false);
      setStep(0);
    }
  }

  const cloudReady = uploadMode === "aws"
    ? !!(cloudCreds.accessKey && cloudCreds.secretKey)
    : !!(cloudCreds.subscriptionId && cloudCreds.tenantId && cloudCreds.clientId && cloudCreds.clientSecret);

  return (
    <div className="flex flex-col items-center">
      {/* Hero section */}
      <div className="text-center mb-10 mt-8">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full mb-6"
          style={{ background: "rgba(201,99,58,0.08)", border: "1px solid rgba(201,99,58,0.12)" }}>
          <div className="w-1.5 h-1.5 rounded-full" style={{ background: C.green }} />
          <span className="text-[11px] font-medium" style={{ color: C.accent }}>Ready to analyze</span>
        </div>
        <h2 className="text-4xl font-semibold tracking-tight mb-3" style={{ color: C.text }}>Connect Your Data</h2>
        <p className="text-base max-w-lg mx-auto" style={{ color: C.muted }}>
          Upload billing exports or connect directly to your cloud account.
        </p>
      </div>

      {/* Mode switcher */}
      <div className="flex gap-1 p-1.5 rounded-xl mb-8" style={{ background: C.border }}>
        {([["files", "Upload Files"], ["aws", "AWS"], ["azure", "Azure"]] as const).map(([mode, label]) => (
          <button key={mode} onClick={() => setUploadMode(mode)}
            className="px-6 py-2 rounded-lg text-sm font-medium cursor-pointer transition-all"
            style={{ background: uploadMode === mode ? C.card : "transparent", color: uploadMode === mode ? C.text : C.muted, border: "none",
              boxShadow: uploadMode === mode ? "0 1px 3px rgba(0,0,0,0.06)" : "none" }}>
            {label}
          </button>
        ))}
      </div>

      <div className="w-full max-w-4xl">
      {/* Cloud connect forms */}
      {uploadMode !== "files" && (
        <div className="mb-5">
          <Card>
            <div className="flex items-center gap-2.5 mb-4">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center"
                style={{ background: uploadMode === "aws" ? "rgba(255,153,0,0.1)" : "rgba(0,120,212,0.1)" }}>
                {uploadMode === "aws" ? (
                  /* AWS — cloud with arrow */
                  <svg width="20" height="16" viewBox="0 0 24 20" fill="none">
                    <path d="M6 16c-2.2 0-4-1.8-4-4 0-1.9 1.3-3.4 3-3.9C5 4.6 7.7 2 11 2c2.8 0 5.2 1.8 6 4.3.5-.2 1-.3 1.5-.3 2.5 0 4.5 2 4.5 4.5S21 15 18.5 15H17" stroke="#FF9900" strokeWidth="1.8" strokeLinecap="round" fill="none"/>
                    <path d="M12 12v6m0 0l-2.5-2.5M12 18l2.5-2.5" stroke="#FF9900" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                ) : (
                  /* Azure — four-tile grid */
                  <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
                    <rect x="1" y="1" width="7" height="7" rx="1.5" fill="#0078D4"/>
                    <rect x="10" y="1" width="7" height="7" rx="1.5" fill="#0078D4" opacity="0.7"/>
                    <rect x="1" y="10" width="7" height="7" rx="1.5" fill="#0078D4" opacity="0.7"/>
                    <rect x="10" y="10" width="7" height="7" rx="1.5" fill="#0078D4" opacity="0.5"/>
                  </svg>
                )}
              </div>
              <div>
                <CardLabel>{uploadMode === "aws" ? "Connect AWS Account" : "Connect Azure Account"}</CardLabel>
                <p className="text-[11px]" style={{ color: C.muted }}>
                  {uploadMode === "aws" ? "Uses Cost Explorer API — requires IAM user with ce:GetCostAndUsage permission" : "Uses Cost Management API — requires an App Registration with Cost Management Reader role"}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {uploadMode === "aws" ? (
                <>
                  <div>
                    <label className="text-[10px] font-medium mb-1 block" style={{ color: C.muted }}>Access Key ID <span style={{ color: C.accent }}>*</span></label>
                    <input placeholder="AKIA..." value={cloudCreds.accessKey || ""} onChange={e => setCloudCreds({ ...cloudCreds, accessKey: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg text-xs outline-none" style={{ border: `1px solid ${C.border}`, color: C.text, background: C.bg }} />
                    <p className="text-[9px] mt-0.5" style={{ color: C.muted }}>IAM → Users → Security credentials</p>
                  </div>
                  <div>
                    <label className="text-[10px] font-medium mb-1 block" style={{ color: C.muted }}>Secret Access Key <span style={{ color: C.accent }}>*</span></label>
                    <input placeholder="wJalrXUtn..." type="password" value={cloudCreds.secretKey || ""} onChange={e => setCloudCreds({ ...cloudCreds, secretKey: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg text-xs outline-none" style={{ border: `1px solid ${C.border}`, color: C.text, background: C.bg }} />
                    <p className="text-[9px] mt-0.5" style={{ color: C.muted }}>Shown once when key is created</p>
                  </div>
                  <div>
                    <label className="text-[10px] font-medium mb-1 block" style={{ color: C.muted }}>Region</label>
                    <input placeholder="us-east-1" value={cloudCreds.region || ""} onChange={e => setCloudCreds({ ...cloudCreds, region: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg text-xs outline-none" style={{ border: `1px solid ${C.border}`, color: C.text, background: C.bg }} />
                    <p className="text-[9px] mt-0.5" style={{ color: C.muted }}>Defaults to us-east-1 if blank</p>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="text-[10px] font-medium mb-1 block" style={{ color: C.muted }}>Subscription ID <span style={{ color: C.accent }}>*</span></label>
                    <input placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" value={cloudCreds.subscriptionId || ""} onChange={e => setCloudCreds({ ...cloudCreds, subscriptionId: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg text-xs outline-none" style={{ border: `1px solid ${C.border}`, color: C.text, background: C.bg }} />
                    <p className="text-[9px] mt-0.5" style={{ color: C.muted }}>Azure Portal → Subscriptions → Overview</p>
                  </div>
                  <div>
                    <label className="text-[10px] font-medium mb-1 block" style={{ color: C.muted }}>Tenant ID (Directory ID) <span style={{ color: C.accent }}>*</span></label>
                    <input placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" value={cloudCreds.tenantId || ""} onChange={e => setCloudCreds({ ...cloudCreds, tenantId: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg text-xs outline-none" style={{ border: `1px solid ${C.border}`, color: C.text, background: C.bg }} />
                    <p className="text-[9px] mt-0.5" style={{ color: C.muted }}>Azure Portal → Microsoft Entra ID → Overview</p>
                  </div>
                  <div>
                    <label className="text-[10px] font-medium mb-1 block" style={{ color: C.muted }}>Client ID (Application ID) <span style={{ color: C.accent }}>*</span></label>
                    <input placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" value={cloudCreds.clientId || ""} onChange={e => setCloudCreds({ ...cloudCreds, clientId: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg text-xs outline-none" style={{ border: `1px solid ${C.border}`, color: C.text, background: C.bg }} />
                    <p className="text-[9px] mt-0.5" style={{ color: C.muted }}>Azure Portal → App registrations → Your app → Overview</p>
                  </div>
                  <div>
                    <label className="text-[10px] font-medium mb-1 block" style={{ color: C.muted }}>Client Secret <span style={{ color: C.accent }}>*</span></label>
                    <input placeholder="Secret value (not Secret ID)" type="password" value={cloudCreds.clientSecret || ""} onChange={e => setCloudCreds({ ...cloudCreds, clientSecret: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg text-xs outline-none" style={{ border: `1px solid ${C.border}`, color: C.text, background: C.bg }} />
                    <p className="text-[9px] mt-0.5" style={{ color: C.muted }}>App registrations → Certificates &amp; secrets → Client secrets → Value</p>
                  </div>
                </>
              )}
              <div>
                <label className="text-[10px] font-medium mb-1 block" style={{ color: C.muted }}>Period</label>
                <select value={cloudMonths} onChange={e => setCloudMonths(Number(e.target.value))}
                  className="w-full px-3 py-2 rounded-lg text-xs outline-none cursor-pointer" style={{ border: `1px solid ${C.border}`, color: C.text, background: C.bg }}>
                  <option value={2}>Last 2 months</option>
                  <option value={3}>Last 3 months</option>
                  <option value={6}>Last 6 months</option>
                  <option value={12}>Last 12 months</option>
                </select>
              </div>
            </div>
            <p className="text-[10px] mt-3" style={{ color: C.muted }}>
              Credentials are used for this session only and are not stored. {uploadMode === "azure" && "The App Registration needs the \"Cost Management Reader\" role assigned on the subscription."}
            </p>
          </Card>

          {/* Optional terraform for cloud connect mode */}
          <div className="mt-4">
            <Card>
              <div className="flex items-center gap-2.5 mb-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "rgba(47,168,79,0.08)" }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.green} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
                  </svg>
                </div>
                <div>
                  <CardLabel>Terraform State <span className="text-[10px] font-normal" style={{ color: C.muted }}>(optional)</span></CardLabel>
                  <p className="text-[11px]" style={{ color: C.muted }}>Upload to enable IaC matching and drift detection</p>
                </div>
              </div>
              {files.terraform ? (
                <div className="flex items-center gap-2 rounded-lg px-3 py-2.5"
                  style={{ background: "rgba(47,168,79,0.04)", border: `1px solid rgba(47,168,79,0.15)` }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={C.green} strokeWidth="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                  <span className="text-xs flex-1 truncate" style={{ color: C.green }}>{files.terraform.name}</span>
                  <button onClick={() => setFiles({ ...files, terraform: null })}
                    className="text-[11px] cursor-pointer shrink-0" style={{ color: C.muted, background: "none", border: "none" }}>&#x2715;</button>
                </div>
              ) : (
                <>
                  <input type="file" accept=".tfstate,.json" className="hidden" id="tf-cloud"
                    onChange={e => { if (e.target.files?.[0]) setFiles({ ...files, terraform: e.target.files[0] }); }} />
                  <button onClick={() => (document.getElementById("tf-cloud") as HTMLInputElement)?.click()}
                    className="w-full py-2.5 rounded-xl text-xs font-medium cursor-pointer"
                    style={{ border: `1.5px dashed ${C.border}`, color: C.muted, background: "transparent" }}>
                    Choose .tfstate file
                  </button>
                </>
              )}
            </Card>
          </div>

          {/* Run button for cloud connect */}
          <button onClick={runCloud} disabled={!cloudReady || running}
            className="cl-btn w-full py-3.5 rounded-xl text-sm font-semibold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed mt-5"
            style={{ background: C.accent, color: "#FFFFFF", border: "none" }}>
            {running ? steps[step - 1] || "Connecting..." : `Connect & Analyze`}
          </button>

          {running && step > 0 && (
            <div className="mt-4">
              <div className="flex gap-1 mb-2">
                {steps.map((_, i) => (
                  <div key={i} className="flex-1 rounded-full h-1.5 overflow-hidden" style={{ background: "#F0EDE6" }}>
                    <div className="h-full rounded-full transition-all duration-500"
                      style={{ width: i < step ? "100%" : i === step ? "60%" : "0%", background: C.accent }} />
                  </div>
                ))}
              </div>
              <p className="text-xs text-center" style={{ color: C.muted }}>Step {step} of {steps.length}</p>
            </div>
          )}
          {error && <p className="text-xs mt-3 text-center" style={{ color: C.red }}>{error}</p>}
        </div>
      )}

      {/* File upload cards */}
      {uploadMode === "files" && (
      <div>
        <div className="grid grid-cols-[1fr_1fr] gap-5 mb-5">
          {/* Billing CSVs */}
          <Card>
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "rgba(201,99,58,0.08)" }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
                </svg>
              </div>
              <div>
                <CardLabel>Billing CSVs</CardLabel>
                <p className="text-[11px]" style={{ color: C.muted }}>2+ months of FOCUS or Azure Cost Export</p>
              </div>
            </div>
            <input ref={billingRef} type="file" accept=".csv" multiple className="hidden"
              onChange={e => {
                const selected = e.target.files ? Array.from(e.target.files) : [];
                if (selected.length > 0) {
                  const existing = files.billingFiles;
                  const existingNames = new Set(existing.map(f => f.name));
                  const newFiles = selected.filter(f => !existingNames.has(f.name));
                  setFiles({ ...files, billingFiles: [...existing, ...newFiles] });
                }
                if (billingRef.current) billingRef.current.value = "";
              }} />
            {files.billingFiles.length > 0 && (
              <div className="space-y-1.5 mb-3">
                {files.billingFiles.map((f, i) => (
                  <div key={f.name} className="flex items-center gap-2 rounded-lg px-3 py-2"
                    style={{ background: "rgba(201,99,58,0.04)", border: `1px solid rgba(201,99,58,0.12)` }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={C.accent} strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span className="text-xs flex-1 truncate" style={{ color: C.accent }}>{f.name}</span>
                    <button onClick={() => setFiles({ ...files, billingFiles: files.billingFiles.filter((_, j) => j !== i) })}
                      className="text-[11px] cursor-pointer shrink-0" style={{ color: C.muted, background: "none", border: "none" }}>&#x2715;</button>
                  </div>
                ))}
              </div>
            )}
            <button onClick={() => billingRef.current?.click()}
              className="cl-btn w-full py-3 rounded-xl text-xs font-medium cursor-pointer"
              style={{ border: `1.5px dashed ${files.billingFiles.length > 0 ? "rgba(201,99,58,0.3)" : C.border}`, color: files.billingFiles.length > 0 ? C.accent : C.muted, background: "transparent" }}>
              + Add CSV {files.billingFiles.length > 0 ? "file" : "files"}
            </button>
            {files.billingFiles.length > 0 && files.billingFiles.length < 2 && (
              <p className="text-[11px] mt-1.5" style={{ color: C.red }}>Add at least 1 more month</p>
            )}
          </Card>

          {/* Terraform State */}
          <Card>
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "rgba(47,168,79,0.08)" }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.green} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
                </svg>
              </div>
              <div>
                <CardLabel>Terraform State</CardLabel>
                <p className="text-[11px]" style={{ color: C.muted }}>.tfstate or .json from your IaC</p>
              </div>
            </div>
            {files.terraform ? (
              <div className="flex items-center gap-2 rounded-lg px-3 py-2.5"
                style={{ background: "rgba(47,168,79,0.04)", border: `1px solid rgba(47,168,79,0.15)` }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={C.green} strokeWidth="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                <span className="text-xs flex-1 truncate" style={{ color: C.green }}>{files.terraform.name}</span>
                <button onClick={() => setFiles({ ...files, terraform: null })}
                  className="text-[11px] cursor-pointer shrink-0" style={{ color: C.muted, background: "none", border: "none" }}>&#x2715;</button>
              </div>
            ) : (
              <>
                <input type="file" accept=".tfstate,.json" className="hidden" id="tf-upload"
                  onChange={e => { if (e.target.files?.[0]) setFiles({ ...files, terraform: e.target.files[0] }); }} />
                <button onClick={() => (document.getElementById("tf-upload") as HTMLInputElement)?.click()}
                  className="cl-btn w-full py-3 rounded-xl text-xs font-medium cursor-pointer"
                  style={{ border: `1.5px dashed ${C.border}`, color: C.muted, background: "transparent" }}>
                  Choose .tfstate file
                </button>
              </>
            )}
          </Card>
        </div>

        {/* Pipeline button */}
        <button
          onClick={run}
          disabled={!ready || running}
          className="cl-btn w-full py-3.5 rounded-xl text-sm font-semibold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ background: C.accent, color: "#FFFFFF", border: "none" }}
        >
          {running ? steps[step - 1] || "Running..." : "Run Pipeline"}
        </button>

        {running && step > 0 && (
          <div className="mt-4">
            <div className="flex gap-1 mb-2">
              {steps.map((_, i) => (
                <div key={i} className="flex-1 rounded-full h-1.5 overflow-hidden" style={{ background: "#F0EDE6" }}>
                  <div className="h-full rounded-full transition-all duration-500"
                    style={{ width: i < step ? "100%" : i === step ? "60%" : "0%", background: C.accent }} />
                </div>
              ))}
            </div>
            <p className="text-xs text-center" style={{ color: C.muted }}>Step {step} of {steps.length}</p>
          </div>
        )}

        {error && <p className="text-xs mt-3 text-center" style={{ color: C.red }}>{error}</p>}
        {!ready && !running && (
          <p className="text-xs mt-3 text-center" style={{ color: C.muted }}>
            Upload at least 2 billing CSVs and a Terraform state file to enable the pipeline.
          </p>
        )}
      </div>
      )}

      {/* What happens next */}
      <div className="w-full max-w-3xl mt-10">
        <div className="grid grid-cols-3 gap-4">
          {[
            { step: "1", title: "Ingest & validate", desc: "CSVs are parsed, deduplicated, and checked for data quality issues." },
            { step: "2", title: "Match & classify", desc: "Each resource is joined against your Terraform state and assigned a reason code." },
            { step: "3", title: "Analyze & export", desc: "Variance is computed with day-normalization. Close packet is ready for your CFO." },
          ].map(s => (
            <div key={s.step} className="flex gap-3">
              <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0"
                style={{ background: "rgba(201,99,58,0.08)", color: C.accent }}>{s.step}</div>
              <div>
                <p className="text-xs font-medium mb-0.5" style={{ color: C.text }}>{s.title}</p>
                <p className="text-[11px] leading-relaxed" style={{ color: C.muted }}>{s.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
      </div>
    </div>
  );
}

/* ═══ Screen 1: Overview (Bill Arrives) ═════════════════════════════════════ */

function OverviewScreen({ prior, current, onData }: { prior: string; current: string; onData?: (d: unknown) => void }) {
  const [data, setData] = useState<{ prior_total: number; current_total: number; delta: number } | null>(null);
  const [variance, setVariance] = useState<{ services: { service: string; abs_delta: number }[]; total_variance: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    api.getBillOverview(prior, current).then(d => { setData(d); onData?.(d); }).catch(e => setError(e.message));
    api.getVarianceByService(current).then(setVariance).catch(() => {});
  }, [prior, current]);
  useEffect(load, [load]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <SkeletonScreen />;

  const pctChange = data.prior_total > 0 ? ((data.delta / data.prior_total) * 100) : 0;

  const allServices = variance?.services || [];
  const maxBar = Math.max(...allServices.map(s => s.abs_delta), 1);

  return (
    <Stagger screenKey={1}>
      {/* KPI row */}
      <div className="grid grid-cols-4 gap-4 mb-4">
        <Card>
          <CardLabel>{shortMonth(prior)} Spend</CardLabel>
          <BigNum sub="Prior month">{fmt(data.prior_total)}</BigNum>
        </Card>
        <Card>
          <CardLabel>{shortMonth(current)} Spend</CardLabel>
          <BigNum>{fmt(data.current_total)}</BigNum>
          <Change value={pctChange} />
        </Card>
        <Card>
          <CardLabel>Variance</CardLabel>
          <BigNum sub="Month-over-month">{data.delta >= 0 ? "+" : ""}{fmt(data.delta)}</BigNum>
        </Card>
        <Card>
          <CardLabel>Change</CardLabel>
          <BigNum sub={`vs ${shortMonth(prior)}`}>{pctChange >= 0 ? "+" : ""}{pctChange.toFixed(1)}%</BigNum>
        </Card>
      </div>

      {/* Service breakdown — full width horizontal bars with tooltips */}
      <Card>
        <CardLabel>Variance by Service</CardLabel>
        <CardSub>{monthLabel(current)}</CardSub>
        <div className="mt-4 space-y-2.5">
          {allServices.slice(0, 8).map(({ service, abs_delta }) => (
            <div key={service} className="flex items-center gap-3 group relative">
              <span className="w-36 text-right text-[13px] shrink-0" style={{ color: C.text }}>{service}</span>
              <div className="flex-1 rounded-full h-6 overflow-hidden" style={{ background: "#F0EDE6" }}>
                <div
                  className="cl-bar h-full rounded-full"
                  style={{ width: `${(abs_delta / maxBar) * 100}%`, background: C.accent }}
                />
              </div>
              <span className="w-20 text-[13px] font-semibold shrink-0 text-right" style={{ color: C.text }}>{fmt(abs_delta)}</span>
              {/* Tooltip on hover */}
              <div
                className="absolute left-40 -top-8 px-2.5 py-1 rounded text-xs font-medium opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-10"
                style={{ background: C.text, color: "#FFFFFF", whiteSpace: "nowrap" }}
              >
                {service}: {fmt(abs_delta)} ({maxBar > 0 ? ((abs_delta / maxBar) * 100).toFixed(0) : 0}% of max)
              </div>
            </div>
          ))}
        </div>
      </Card>
    </Stagger>
  );
}

/* ═══ Screen 2: Ingestion ═══════════════════════════════════════════════════ */

function QualityDot({ ok }: { ok: boolean }) {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full mr-2 shrink-0"
      style={{ background: ok ? C.green : C.red, marginTop: 1 }}
    />
  );
}

function IngestionScreen({ current, onData }: { current: string; onData?: (d: unknown) => void }) {
  const [data, setData] = useState<{
    billing_rows: number; current_period_rows: number; resource_count: number;
    terraform_resources: number; terraform_matched_cost: number; terraform_unmatched_cost: number;
    total_cost: number; coverage_pct: number; unattributed: number;
    period_breakdown: { period: string; rows: number; cost: number; unique_resources: number }[];
    data_quality: { missing_resource_id: number; missing_service: number; zero_cost_lines: number; negative_cost_lines: number };
    tag_coverage: { tagged_resources: number; tagged_cost: number; total_resources: number; total_cost: number };
    services: { service: string; rows: number; cost: number; resources: number; terraform_matched: number }[];
    top_unmatched: { resource_id: string; resource_name: string | null; service: string | null; cost: number }[];
    detected_providers: string[];
  } | null>(null);

  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { setError(null); api.getIngestionStats(current).then(d => { setData(d); onData?.(d); }).catch(e => setError(e.message)); }, [current]);
  useEffect(load, [load]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <SkeletonScreen />;

  const tfPct = data.resource_count > 0 ? (data.terraform_resources / data.resource_count) * 100 : 0;
  const tfCostPct = data.total_cost > 0 ? (data.terraform_matched_cost / data.total_cost) * 100 : 0;
  const tagPct = data.tag_coverage.total_resources > 0
    ? (data.tag_coverage.tagged_resources / data.tag_coverage.total_resources) * 100 : 0;
  const tagCostPct = data.tag_coverage.total_cost > 0
    ? (data.tag_coverage.tagged_cost / data.tag_coverage.total_cost) * 100 : 0;
  const dq = data.data_quality;
  const qualityIssues = dq.missing_resource_id + dq.missing_service + dq.zero_cost_lines;
  const allClean = qualityIssues === 0 && dq.negative_cost_lines === 0;

  return (
    <Stagger screenKey={2}>
      {/* Row 1: File parsing results */}
      <Card className="mb-4">
        <div className="flex items-center justify-between mb-3">
          <CardLabel>Files Parsed</CardLabel>
          <span className="text-xs px-2.5 py-0.5 rounded-full font-medium"
            style={{ background: "rgba(47,168,79,0.1)", color: C.green }}>
            {data.detected_providers.join(", ") || "Unknown"} detected
          </span>
        </div>
        <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${data.period_breakdown.length}, 1fr)` }}>
          {data.period_breakdown.map(p => {
            const isCurrentPeriod = p.period === current;
            return (
              <div key={p.period} className="rounded-lg p-4"
                style={{
                  background: isCurrentPeriod ? "rgba(201,99,58,0.04)" : "#FAFAF8",
                  border: `1px solid ${isCurrentPeriod ? C.accent : C.border}`,
                }}>
                <p className="text-xs font-medium mb-2" style={{ color: isCurrentPeriod ? C.accent : C.muted }}>
                  {(() => { const [y, m] = p.period.split("-"); return new Date(+y, +m - 1).toLocaleDateString("en-US", { month: "long", year: "numeric" }); })()}
                  {isCurrentPeriod && <span className="ml-1.5 text-[10px] opacity-70">(current)</span>}
                </p>
                <p className="text-xl font-semibold mb-1" style={{ color: C.text }}>{p.rows.toLocaleString()} <span className="text-xs font-normal" style={{ color: C.muted }}>rows</span></p>
                <div className="flex gap-4 text-xs" style={{ color: C.muted }}>
                  <span>{p.unique_resources} resources</span>
                  <span>{fmt(p.cost)}</span>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Row 2: Terraform matching + Tag coverage */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <Card>
          <CardLabel>Terraform Matching</CardLabel>
          <p className="text-xs mt-0.5 mb-3" style={{ color: C.muted }}>
            {data.terraform_resources} of {data.resource_count} resources found in .tfstate
          </p>
          <div className="mb-3">
            <div className="flex items-center justify-between text-xs mb-1">
              <span style={{ color: C.muted }}>By resource count</span>
              <span className="font-medium" style={{ color: tfPct > 50 ? C.green : C.red }}>{tfPct.toFixed(0)}%</span>
            </div>
            <div className="rounded-full h-2.5 overflow-hidden flex" style={{ background: "#F0EDE6" }}>
              <div className="h-full rounded-l-full" style={{ width: `${tfPct}%`, background: C.accent }} />
            </div>
            <div className="flex justify-between text-[11px] mt-1" style={{ color: C.muted }}>
              <span>{data.terraform_resources} matched</span>
              <span>{data.resource_count - data.terraform_resources} unmatched</span>
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span style={{ color: C.muted }}>By cost</span>
              <span className="font-medium" style={{ color: tfCostPct > 50 ? C.green : C.red }}>{tfCostPct.toFixed(0)}%</span>
            </div>
            <div className="rounded-full h-2.5 overflow-hidden flex" style={{ background: "#F0EDE6" }}>
              <div className="h-full rounded-l-full" style={{ width: `${tfCostPct}%`, background: C.accent }} />
            </div>
            <div className="flex justify-between text-[11px] mt-1" style={{ color: C.muted }}>
              <span>{fmt(data.terraform_matched_cost)} managed</span>
              <span>{fmt(data.terraform_unmatched_cost)} unmanaged</span>
            </div>
          </div>
        </Card>

        <Card>
          <CardLabel>Team Attribution</CardLabel>
          <p className="text-xs mt-0.5 mb-3" style={{ color: C.muted }}>
            Resources with a &quot;team&quot; tag in billing data
          </p>
          <div className="mb-3">
            <div className="flex items-center justify-between text-xs mb-1">
              <span style={{ color: C.muted }}>By resource count</span>
              <span className="font-medium" style={{ color: tagPct > 50 ? C.green : C.red }}>{tagPct.toFixed(0)}%</span>
            </div>
            <div className="rounded-full h-2.5 overflow-hidden flex" style={{ background: "#F0EDE6" }}>
              <div className="h-full rounded-l-full" style={{ width: `${tagPct}%`, background: C.accent }} />
            </div>
            <div className="flex justify-between text-[11px] mt-1" style={{ color: C.muted }}>
              <span>{data.tag_coverage.tagged_resources} tagged</span>
              <span>{data.tag_coverage.total_resources - data.tag_coverage.tagged_resources} untagged</span>
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span style={{ color: C.muted }}>By cost</span>
              <span className="font-medium" style={{ color: tagCostPct > 50 ? C.green : C.red }}>{tagCostPct.toFixed(0)}%</span>
            </div>
            <div className="rounded-full h-2.5 overflow-hidden flex" style={{ background: "#F0EDE6" }}>
              <div className="h-full rounded-l-full" style={{ width: `${tagCostPct}%`, background: C.accent }} />
            </div>
            <div className="flex justify-between text-[11px] mt-1" style={{ color: C.muted }}>
              <span>{fmt(data.tag_coverage.tagged_cost)} attributed</span>
              <span>{fmt(data.total_cost - data.tag_coverage.tagged_cost)} unattributed</span>
            </div>
          </div>
        </Card>
      </div>

      {/* Row 3: Data quality + Service breakdown */}
      <div className="grid grid-cols-[280px_1fr] gap-4 mb-4">
        <Card>
          <div className="flex items-center justify-between mb-3">
            <CardLabel>Data Quality</CardLabel>
            {allClean ? (
              <span className="text-[11px] px-2 py-0.5 rounded-full font-medium"
                style={{ background: "rgba(47,168,79,0.1)", color: C.green }}>All clear</span>
            ) : (
              <span className="text-[11px] px-2 py-0.5 rounded-full font-medium"
                style={{ background: "rgba(217,68,68,0.1)", color: C.red }}>{qualityIssues + (dq.negative_cost_lines > 0 ? 1 : 0)} issues</span>
            )}
          </div>
          <div className="space-y-2.5">
            <div className="flex items-center text-xs" style={{ color: C.text }}>
              <QualityDot ok={dq.missing_resource_id === 0} />
              <span className="flex-1">Resource IDs</span>
              <span style={{ color: dq.missing_resource_id === 0 ? C.green : C.red }}>
                {dq.missing_resource_id === 0 ? "Complete" : `${dq.missing_resource_id} missing`}
              </span>
            </div>
            <div className="flex items-center text-xs" style={{ color: C.text }}>
              <QualityDot ok={dq.missing_service === 0} />
              <span className="flex-1">Service names</span>
              <span style={{ color: dq.missing_service === 0 ? C.green : C.red }}>
                {dq.missing_service === 0 ? "Complete" : `${dq.missing_service} missing`}
              </span>
            </div>
            <div className="flex items-center text-xs" style={{ color: C.text }}>
              <QualityDot ok={dq.zero_cost_lines === 0} />
              <span className="flex-1">Zero-cost lines</span>
              <span style={{ color: dq.zero_cost_lines === 0 ? C.green : C.muted }}>
                {dq.zero_cost_lines === 0 ? "None" : `${dq.zero_cost_lines} rows`}
              </span>
            </div>
            <div className="flex items-center text-xs" style={{ color: C.text }}>
              <QualityDot ok={dq.negative_cost_lines === 0} />
              <span className="flex-1">Credits / refunds</span>
              <span style={{ color: C.muted }}>
                {dq.negative_cost_lines === 0 ? "None" : `${dq.negative_cost_lines} rows`}
              </span>
            </div>
          </div>
        </Card>

        <Card>
          <CardLabel>Coverage by Service</CardLabel>
          <table className="cl-table w-full mt-2 text-xs">
            <thead>
              <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                <th className="text-left py-2 font-medium" style={{ color: C.muted }}>Service</th>
                <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Cost</th>
                <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Resources</th>
                <th className="text-right py-2 font-medium pr-1" style={{ color: C.muted }}>Terraform</th>
                <th className="py-2 font-medium w-24" style={{ color: C.muted }}></th>
              </tr>
            </thead>
            <tbody>
              {data.services.slice(0, 6).map(svc => {
                const matchPct = svc.resources > 0 ? (svc.terraform_matched / svc.resources) * 100 : 0;
                return (
                  <tr key={svc.service} style={{ borderBottom: `1px solid ${C.border}` }}>
                    <td className="py-2" style={{ color: C.text }}>{svc.service}</td>
                    <td className="py-2 text-right font-medium" style={{ color: C.accent }}>{fmt(svc.cost)}</td>
                    <td className="py-2 text-right" style={{ color: C.text }}>{svc.resources}</td>
                    <td className="py-2 text-right pr-1" style={{ color: matchPct === 100 ? C.green : matchPct > 0 ? C.accent : C.red }}>
                      {svc.terraform_matched}/{svc.resources}
                    </td>
                    <td className="py-2 pl-2">
                      <div className="rounded-full h-1.5 overflow-hidden" style={{ background: "#F0EDE6" }}>
                        <div className="h-full rounded-full" style={{ width: `${matchPct}%`, background: matchPct === 100 ? C.green : C.accent }} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </div>

      {/* Row 4: Top unmatched resources */}
      {data.top_unmatched.length > 0 && (
        <Card>
          <CardLabel>Top Unmatched Resources</CardLabel>
          <p className="text-xs mb-3" style={{ color: C.muted }}>
            Highest-cost resources not found in Terraform state
          </p>
          <div className="space-y-2">
            {data.top_unmatched.map((r, i) => (
              <div key={i} className="cl-row-item flex items-center gap-3 rounded-lg px-3 py-2"
                style={{ background: "#FAFAF8", border: `1px solid ${C.border}` }}>
                <span className="text-xs font-medium shrink-0" style={{ color: C.red }}>
                  {fmt(r.cost)}
                </span>
                <span className="text-xs truncate flex-1" style={{ color: C.text }}>
                  {r.resource_name || r.resource_id}
                </span>
                <span className="text-[11px] shrink-0" style={{ color: C.muted }}>
                  {r.service || ""}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </Stagger>
  );
}

/* ═══ Screen 3: Variance ════════════════════════════════════════════════════ */

function VarianceScreen({ current, onData }: { current: string; onData?: (d: unknown) => void }) {
  type VData = {
    services: { service: string; delta: number; abs_delta: number; count: number; prior_cost: number; current_cost: number }[];
    resources: { resource_id: string; resource_name: string | null; service: string; prior_cost: number; current_cost: number; delta: number; delta_pct: number; reason_code: string; in_terraform: boolean; evidence: string | null; team: string | null }[];
    reasons: { code: string; delta: number; abs_delta: number; count: number }[];
    total_variance: number; total_increases: number; total_decreases: number; net_change: number;
  };
  const [data, setData] = useState<VData | null>(null);
  const [filterReason, setFilterReason] = useState<string | null>(null);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { setError(null); api.getVarianceByService(current).then(d => { setData(d); onData?.(d); }).catch(e => setError(e.message)); }, [current]);
  useEffect(load, [load]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <SkeletonScreen />;

  const filtered = filterReason
    ? data.resources.filter(r => r.reason_code === filterReason)
    : data.resources;

  return (
    <Stagger screenKey={3}>
      {/* Row 1: Summary KPIs */}
      <div className="grid grid-cols-4 gap-4 mb-4">
        <Card>
          <CardLabel>Net Change</CardLabel>
          <BigNum>{data.net_change >= 0 ? "+" : ""}{fmt(data.net_change)}</BigNum>
          <CardSub>{data.resources.length} resources changed</CardSub>
        </Card>
        <Card>
          <CardLabel>Increases</CardLabel>
          <p className="text-2xl font-semibold" style={{ color: C.red }}>+{fmt(data.total_increases)}</p>
          <CardSub>{data.resources.filter(r => r.delta > 0).length} resources</CardSub>
        </Card>
        <Card>
          <CardLabel>Decreases</CardLabel>
          <p className="text-2xl font-semibold" style={{ color: C.green }}>{fmt(data.total_decreases)}</p>
          <CardSub>{data.resources.filter(r => r.delta < 0).length} resources</CardSub>
        </Card>
        <Card>
          <CardLabel>Abs. Variance</CardLabel>
          <BigNum>{fmt(data.total_variance)}</BigNum>
          <CardSub>Total movement</CardSub>
        </Card>
      </div>

      {/* Row 2: Service breakdown + Reason breakdown */}
      <div className="grid grid-cols-[1fr_280px] gap-4 mb-4">
        {/* Service table with prior/current/delta */}
        <Card>
          <CardLabel>Variance by Service</CardLabel>
          <table className="cl-table w-full mt-2 text-xs">
            <thead>
              <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                <th className="text-left py-2 font-medium" style={{ color: C.muted }}>Service</th>
                <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Prior</th>
                <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Current</th>
                <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Delta</th>
                <th className="text-right py-2 font-medium" style={{ color: C.muted }}>%</th>
              </tr>
            </thead>
            <tbody>
              {data.services.map(svc => {
                const pct = svc.prior_cost > 0 ? ((svc.delta / svc.prior_cost) * 100) : (svc.current_cost > 0 ? 100 : 0);
                return (
                  <tr key={svc.service} style={{ borderBottom: `1px solid ${C.border}` }}>
                    <td className="py-2.5" style={{ color: C.text }}>{svc.service} <span className="text-[10px]" style={{ color: C.muted }}>({svc.count})</span></td>
                    <td className="py-2.5 text-right" style={{ color: C.muted }}>{fmt(svc.prior_cost)}</td>
                    <td className="py-2.5 text-right" style={{ color: C.text }}>{fmt(svc.current_cost)}</td>
                    <td className="py-2.5 text-right font-medium" style={{ color: svc.delta > 0 ? C.red : svc.delta < 0 ? C.green : C.muted }}>
                      {svc.delta > 0 ? "+" : ""}{fmt(svc.delta)}
                    </td>
                    <td className="py-2.5 text-right" style={{ color: svc.delta > 0 ? C.red : svc.delta < 0 ? C.green : C.muted }}>
                      {pct > 0 ? "+" : ""}{pct.toFixed(1)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>

        {/* Reason code breakdown */}
        <Card>
          <CardLabel>By Reason Code</CardLabel>
          <p className="text-[11px] mb-3" style={{ color: C.muted }}>Click to filter the table below</p>
          <div className="space-y-2">
            {data.reasons.map(r => {
              const isActive = filterReason === r.code;
              return (
                <button key={r.code}
                  onClick={() => setFilterReason(isActive ? null : r.code)}
                  className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-left cursor-pointer transition-all"
                  style={{
                    background: isActive ? "rgba(201,99,58,0.08)" : "#FAFAF8",
                    border: `1px solid ${isActive ? C.accent : C.border}`,
                  }}>
                  <ReasonBadge code={r.code} />
                  <span className="flex-1 text-xs" style={{ color: C.text }}>{r.count}</span>
                  <span className="text-xs font-medium" style={{ color: r.delta > 0 ? C.red : r.delta < 0 ? C.green : C.muted }}>
                    {r.delta > 0 ? "+" : ""}{fmt(r.delta)}
                  </span>
                </button>
              );
            })}
            {filterReason && (
              <button onClick={() => setFilterReason(null)}
                className="w-full text-[11px] py-1 cursor-pointer"
                style={{ color: C.muted, background: "none", border: "none", textDecoration: "underline" }}>
                Clear filter
              </button>
            )}
          </div>
        </Card>
      </div>

      {/* Row 3: Resource-level detail table */}
      <Card>
        <div className="flex items-center justify-between mb-2">
          <CardLabel>Resource Detail{filterReason ? ` — ${filterReason.replace(/_/g, " ")}` : ""}</CardLabel>
          <span className="text-xs" style={{ color: C.muted }}>{filtered.length} resources</span>
        </div>
        <div style={{ maxHeight: 400, overflowY: "auto" }}>
          <table className="cl-table w-full text-xs">
            <thead style={{ position: "sticky", top: 0, background: C.card }}>
              <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                <th className="text-left py-2 font-medium" style={{ color: C.muted }}>Resource</th>
                <th className="text-left py-2 font-medium" style={{ color: C.muted }}>Service</th>
                <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Prior</th>
                <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Current</th>
                <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Delta</th>
                <th className="text-right py-2 font-medium" style={{ color: C.muted }}>%</th>
                <th className="text-left py-2 font-medium pl-3" style={{ color: C.muted }}>Reason</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => {
                const isOpen = expandedRow === i;
                return (
                  <React.Fragment key={i}>
                    <tr style={{ borderBottom: isOpen ? "none" : `1px solid ${C.border}`, cursor: "pointer", background: isOpen ? "rgba(201,99,58,0.03)" : undefined }}
                      onClick={() => setExpandedRow(isOpen ? null : i)}>
                      <td className="py-2 max-w-[200px]" style={{ color: C.text }}>
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] shrink-0" style={{ color: C.muted, transition: "transform 0.2s", transform: isOpen ? "rotate(90deg)" : "rotate(0)" }}>&#9654;</span>
                          <div>
                            <div className="truncate">{r.resource_name || r.resource_id}</div>
                            {r.team && <span className="text-[10px]" style={{ color: C.muted }}>{r.team}</span>}
                          </div>
                        </div>
                      </td>
                      <td className="py-2" style={{ color: C.muted }}>{r.service}</td>
                      <td className="py-2 text-right" style={{ color: C.muted }}>{fmt(r.prior_cost)}</td>
                      <td className="py-2 text-right" style={{ color: C.text }}>{fmt(r.current_cost)}</td>
                      <td className="py-2 text-right font-medium" style={{ color: r.delta > 0 ? C.red : r.delta < 0 ? C.green : C.muted }}>
                        {r.delta > 0 ? "+" : ""}{fmt(r.delta)}
                      </td>
                      <td className="py-2 text-right" style={{ color: r.delta > 0 ? C.red : r.delta < 0 ? C.green : C.muted }}>
                        {r.delta_pct > 0 ? "+" : ""}{r.delta_pct.toFixed(1)}%
                      </td>
                      <td className="py-2 pl-3">
                        <div className="flex items-center gap-1.5">
                          <ReasonBadge code={r.reason_code} />
                          {r.in_terraform && (
                            <span className="text-[10px] px-1 py-0.5 rounded" style={{ background: "rgba(47,168,79,0.1)", color: C.green }}>TF</span>
                          )}
                        </div>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                        <td colSpan={7} className="py-0">
                          <div className="rounded-xl mx-2 mb-3 p-4" style={{ background: "#FAFAF8", border: `1px solid ${C.border}` }}>
                            <div className="grid grid-cols-3 gap-4 mb-3">
                              <div>
                                <p className="text-[10px] font-medium mb-0.5" style={{ color: C.muted }}>Resource ID <button onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(r.resource_id); }} className="cursor-pointer" style={{ background: "none", border: "none", color: C.accent, fontSize: 10 }} title="Copy to clipboard">copy</button></p>
                                <p className="text-[11px] break-all" style={{ color: C.text }}>{r.resource_id}</p>
                              </div>
                              <div>
                                <p className="text-[10px] font-medium mb-0.5" style={{ color: C.muted }}>IaC Status</p>
                                <p className="text-[11px]" style={{ color: r.in_terraform ? C.green : C.red }}>
                                  {r.in_terraform ? "Managed by Terraform" : "Not in any IaC state"}
                                </p>
                              </div>
                              <div>
                                <p className="text-[10px] font-medium mb-0.5" style={{ color: C.muted }}>Cost Breakdown</p>
                                <div className="flex rounded-full h-2 overflow-hidden" style={{ background: "#E8E6DE" }}>
                                  {r.prior_cost > 0 && <div style={{ width: `${Math.max(r.prior_cost / Math.max(r.prior_cost, r.current_cost) * 100, 2)}%`, background: C.muted }} />}
                                  {r.current_cost > 0 && <div style={{ width: `${Math.max(r.current_cost / Math.max(r.prior_cost, r.current_cost) * 100, 2)}%`, background: C.accent }} />}
                                </div>
                                <div className="flex justify-between text-[10px] mt-0.5" style={{ color: C.muted }}>
                                  <span>Prior: {fmt(r.prior_cost)}</span>
                                  <span>Current: {fmt(r.current_cost)}</span>
                                </div>
                              </div>
                            </div>
                            {r.evidence && (
                              <div className="mb-2">
                                <p className="text-[10px] font-medium mb-0.5" style={{ color: C.muted }}>Evidence</p>
                                <p className="text-[11px]" style={{ color: C.text }}>{r.evidence}</p>
                              </div>
                            )}
                            <div>
                              <p className="text-[10px] font-medium mb-0.5" style={{ color: C.muted }}>Why this classification?</p>
                              <p className="text-[11px] leading-relaxed" style={{ color: C.text }}>
                                {REASON_EXPLAIN[r.reason_code] || `Classified as "${r.reason_code.replace(/_/g, " ")}" based on IaC state matching and change event analysis.`}
                              </p>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </Stagger>
  );
}

/* ═══ Screen 4: Root Causes ═════════════════════════════════════════════════ */

function BucketCard({ label, desc, color, bucket }: {
  label: string; desc: string; color: string;
  bucket: { amount: number; delta: number; count: number; top_resources: { resource_name: string | null; resource_id: string; service: string; delta: number; reason_code: string; evidence: string | null }[] };
}) {
  const [expanded, setExpanded] = useState<number | null>(null);
  if (bucket.count === 0) return null;
  return (
    <Card>
      <div className="flex items-center justify-between mb-1">
        <CardLabel>{label}</CardLabel>
        <span className="text-[10px] px-2 py-0.5 rounded-full font-medium"
          style={{ background: `${color}18`, color }}>{bucket.count} resources</span>
      </div>
      <p className="text-[11px] mb-3" style={{ color: C.muted }}>{desc}</p>
      <p className="text-2xl font-semibold tracking-tight mb-3" style={{ color, fontVariantNumeric: "tabular-nums" }}>
        {bucket.delta > 0 ? "+" : ""}{fmt(bucket.delta)}
      </p>
      {bucket.top_resources.length > 0 && (
        <div className="space-y-1.5">
          {bucket.top_resources.map((r, i) => (
            <div key={i}>
              <div className="cl-row-item flex items-center gap-2 rounded-lg px-2.5 py-1.5 cursor-pointer"
                onClick={() => setExpanded(expanded === i ? null : i)}
                style={{ background: expanded === i ? "rgba(201,99,58,0.04)" : "#FAFAF8", border: `1px solid ${expanded === i ? "rgba(201,99,58,0.2)" : C.border}` }}>
                <span className="text-[10px] shrink-0" style={{ color: C.muted, transition: "transform 0.2s", transform: expanded === i ? "rotate(90deg)" : "rotate(0)" }}>&#9654;</span>
                <span className="text-xs font-medium shrink-0" style={{ color: r.delta > 0 ? C.red : C.green }}>
                  {r.delta > 0 ? "+" : ""}{fmt(r.delta)}
                </span>
                <span className="text-xs truncate flex-1" style={{ color: C.text }}>
                  {r.resource_name || r.resource_id}
                </span>
                <span className="text-[10px] shrink-0" style={{ color: C.muted }}>{r.service}</span>
              </div>
              {expanded === i && (
                <div className="ml-4 mt-1 mb-2 rounded-lg p-3 text-[11px]" style={{ background: "#FAFAF8", border: `1px solid ${C.border}` }}>
                  <div className="grid grid-cols-2 gap-2 mb-2">
                    <div>
                      <span style={{ color: C.muted }}>Reason: </span>
                      <ReasonBadge code={r.reason_code} />
                    </div>
                    <div>
                      <span style={{ color: C.muted }}>Service: </span>
                      <span style={{ color: C.text }}>{r.service}</span>
                    </div>
                  </div>
                  {r.evidence && (
                    <div className="mb-2">
                      <span style={{ color: C.muted }}>Evidence: </span>
                      <span style={{ color: C.text }}>{r.evidence}</span>
                    </div>
                  )}
                  <div>
                    <span style={{ color: C.muted }}>Explanation: </span>
                    <span style={{ color: C.text }}>{REASON_EXPLAIN[r.reason_code] || "No additional detail available."}</span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function RootCausesScreen({ current, onData }: { current: string; onData?: (d: unknown) => void }) {
  type Bucket = { amount: number; delta: number; count: number; top_resources: { resource_id: string; resource_name: string | null; service: string; delta: number; prior_cost: number; current_cost: number; reason_code: string; evidence: string | null; in_terraform: boolean; team: string | null }[] };
  const [data, setData] = useState<{
    planned: Bucket; drift: Bucket; usage: Bucket; edge_cases: Bucket;
    all_reasons: { code: string; delta: number; abs_delta: number; count: number }[];
  } | null>(null);

  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { setError(null); api.getRootCauses(current).then(d => { setData(d); onData?.(d); }).catch(e => setError(e.message)); }, [current]);
  useEffect(load, [load]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <SkeletonScreen />;

  const total = data.planned.amount + data.drift.amount + data.usage.amount + data.edge_cases.amount;
  const buckets = [
    { key: "planned", label: "Planned Changes", desc: "In Terraform + linked to a change event", color: C.green, bucket: data.planned },
    { key: "drift", label: "Unmanaged / Drift", desc: "Not in any IaC state — needs investigation", color: C.red, bucket: data.drift },
    { key: "usage", label: "Usage & Lifecycle", desc: "New, removed, or organically growing resources", color: C.accent, bucket: data.usage },
    { key: "edge", label: "Edge Cases", desc: "Credits, savings plans, spot pricing, transfers", color: C.muted, bucket: data.edge_cases },
  ].filter(b => b.bucket.count > 0);

  return (
    <Stagger screenKey={4}>
      {/* Proportional bar */}
      <Card className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <CardLabel>Variance Attribution</CardLabel>
          <span className="text-xs" style={{ color: C.muted }}>{fmt(total)} total movement</span>
        </div>
        <div className="flex rounded-full h-5 overflow-hidden" style={{ background: "#F0EDE6" }}>
          {buckets.map(b => (
            <div key={b.key} style={{ width: `${total > 0 ? (b.bucket.amount / total) * 100 : 0}%`, background: b.color }}
              title={`${b.label}: ${fmt(b.bucket.amount)}`} />
          ))}
        </div>
        <div className="flex gap-5 mt-2.5">
          {buckets.map(b => (
            <div key={b.key} className="flex items-center gap-1.5 text-xs" style={{ color: C.text }}>
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: b.color }} />
              {b.label} ({b.bucket.count})
            </div>
          ))}
        </div>
      </Card>

      {/* Bucket detail cards */}
      <div className={`grid gap-4 mb-4`} style={{ gridTemplateColumns: `repeat(${Math.min(buckets.length, 2)}, 1fr)` }}>
        {buckets.map(b => (
          <BucketCard key={b.key} label={b.label} desc={b.desc} color={b.color} bucket={b.bucket} />
        ))}
      </div>

      {/* Granular reason code table */}
      <Card>
        <CardLabel>All Reason Codes</CardLabel>
        <table className="cl-table w-full mt-2 text-xs">
          <thead>
            <tr style={{ borderBottom: `1px solid ${C.border}` }}>
              <th className="text-left py-2 font-medium" style={{ color: C.muted }}>Reason</th>
              <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Resources</th>
              <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Net Delta</th>
              <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Abs. Movement</th>
              <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Share</th>
            </tr>
          </thead>
          <tbody>
            {data.all_reasons.map(r => (
              <tr key={r.code} style={{ borderBottom: `1px solid ${C.border}` }}>
                <td className="py-2" style={{ color: C.text }}>
                  <ReasonBadge code={r.code} />
                </td>
                <td className="py-2 text-right" style={{ color: C.text }}>{r.count}</td>
                <td className="py-2 text-right font-medium" style={{ color: r.delta > 0 ? C.red : r.delta < 0 ? C.green : C.muted }}>
                  {r.delta > 0 ? "+" : ""}{fmt(r.delta)}
                </td>
                <td className="py-2 text-right" style={{ color: C.accent }}>{fmt(r.abs_delta)}</td>
                <td className="py-2 text-right" style={{ color: C.muted }}>
                  {total > 0 ? ((r.abs_delta / total) * 100).toFixed(1) : 0}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </Stagger>
  );
}

/* ═══ Screen 5: Close Packet ════════════════════════════════════════════════ */

function ClosePacketScreen({ current, prior, onData }: { current: string; prior: string; onData?: (d: unknown) => void }) {
  const [data, setData] = useState<{
    prior_cost: number; total_cost: number; net_variance: number; total_variance: number;
    reasons: { code: string; delta: number; abs_delta: number; count: number; top_resources: { name: string; delta: number; service: string }[] }[];
    resource_count: number; managed_count: number; managed_cost: number;
    action_items: { resource_name: string; service: string; delta: number; reason: string; action: string }[];
  } | null>(null);

  const [expandedReason, setExpandedReason] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { setError(null); api.getClosePacket(current, prior).then(d => { setData(d); onData?.(d); }).catch(e => setError(e.message)); }, [current, prior]);
  useEffect(load, [load]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <SkeletonScreen />;

  const pctChange = data.prior_cost > 0 ? ((data.net_variance / data.prior_cost) * 100) : 0;
  const managedPct = data.resource_count > 0 ? ((data.managed_count / data.resource_count) * 100) : 0;

  return (
    <Stagger screenKey={5}>
      {/* Summary narrative */}
      <Card className="mb-4">
        <CardLabel>Month-End Summary — {monthLabel(current)}</CardLabel>
        <p className="text-sm mt-2 leading-relaxed" style={{ color: C.text }}>
          Cloud spend {data.net_variance >= 0 ? "increased" : "decreased"} by <strong>{data.net_variance >= 0 ? "+" : ""}{fmt(data.net_variance)}</strong> ({pctChange >= 0 ? "+" : ""}{pctChange.toFixed(1)}%) from {fmt(data.prior_cost)} to {fmt(data.total_cost)}.
          {" "}{data.resource_count} resources were analyzed across {data.reasons.length} reason categories.
          {data.managed_count > 0 && <> {managedPct.toFixed(0)}% of resources ({data.managed_count} of {data.resource_count}) are managed by Terraform.</>}
          {data.action_items.length > 0 && <> {data.action_items.length} drift items require follow-up.</>}
        </p>
      </Card>

      {/* KPI row */}
      <div className="grid grid-cols-4 gap-4 mb-4">
        <Card>
          <CardLabel>Prior Month</CardLabel>
          <BigNum>{fmt(data.prior_cost)}</BigNum>
          <CardSub>{shortMonth(prior)}</CardSub>
        </Card>
        <Card>
          <CardLabel>Current Month</CardLabel>
          <BigNum>{fmt(data.total_cost)}</BigNum>
          <CardSub>{shortMonth(current)}</CardSub>
        </Card>
        <Card>
          <CardLabel>Net Change</CardLabel>
          <p className="text-2xl font-semibold" style={{ color: data.net_variance > 0 ? C.red : C.green }}>
            {data.net_variance > 0 ? "+" : ""}{fmt(data.net_variance)}
          </p>
          <CardSub>{pctChange >= 0 ? "+" : ""}{pctChange.toFixed(1)}%</CardSub>
        </Card>
        <Card>
          <CardLabel>IaC Coverage</CardLabel>
          <BigNum>{managedPct.toFixed(0)}%</BigNum>
          <CardSub>{data.managed_count} of {data.resource_count} resources</CardSub>
        </Card>
      </div>

      {/* Variance breakdown table with inline evidence */}
      <Card className="mb-4">
        <CardLabel>Variance Breakdown</CardLabel>
        <table className="cl-table w-full mt-2 text-xs">
          <thead>
            <tr style={{ borderBottom: `1px solid ${C.border}` }}>
              <th className="text-left py-2 font-medium" style={{ color: C.muted }}>Reason Code</th>
              <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Resources</th>
              <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Net Delta</th>
              <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Share</th>
              <th className="text-left py-2 font-medium pl-4" style={{ color: C.muted }}>Top Contributors</th>
            </tr>
          </thead>
          <tbody>
            {data.reasons.map(r => {
              const isOpen = expandedReason === r.code;
              return (
                <React.Fragment key={r.code}>
                  <tr style={{ borderBottom: isOpen ? "none" : `1px solid ${C.border}`, cursor: "pointer", background: isOpen ? "rgba(201,99,58,0.03)" : undefined }}
                    onClick={() => setExpandedReason(isOpen ? null : r.code)}>
                    <td className="py-2.5">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px]" style={{ color: C.muted, transition: "transform 0.2s", transform: isOpen ? "rotate(90deg)" : "rotate(0)" }}>&#9654;</span>
                        <ReasonBadge code={r.code} />
                      </div>
                    </td>
                    <td className="py-2.5 text-right" style={{ color: C.text }}>{r.count}</td>
                    <td className="py-2.5 text-right font-medium" style={{ color: r.delta > 0 ? C.red : r.delta < 0 ? C.green : C.muted }}>
                      {r.delta > 0 ? "+" : ""}{fmt(r.delta)}
                    </td>
                    <td className="py-2.5 text-right" style={{ color: C.muted }}>
                      {data.total_variance > 0 ? ((r.abs_delta / data.total_variance) * 100).toFixed(1) : 0}%
                    </td>
                    <td className="py-2.5 pl-4" style={{ color: C.muted }}>
                      {r.top_resources.slice(0, 2).map((res, ri) => (
                        <span key={ri} className="text-[11px]">
                          {ri > 0 && ", "}
                          {res.name} <span style={{ color: res.delta > 0 ? C.red : C.green }}>({res.delta > 0 ? "+" : ""}{fmt(res.delta)})</span>
                        </span>
                      ))}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                      <td colSpan={5} className="py-0">
                        <div className="rounded-xl mx-2 mb-3 p-4" style={{ background: "#FAFAF8", border: `1px solid ${C.border}` }}>
                          <p className="text-[11px] leading-relaxed mb-3" style={{ color: C.text }}>
                            {REASON_EXPLAIN[r.code] || `Resources classified as "${r.code.replace(/_/g, " ")}".`}
                          </p>
                          <p className="text-[10px] font-medium mb-1.5" style={{ color: C.muted }}>Contributing resources</p>
                          <div className="space-y-1">
                            {r.top_resources.map((res, ri) => (
                              <div key={ri} className="flex items-center gap-2 text-[11px]">
                                <span className="font-medium" style={{ color: res.delta > 0 ? C.red : C.green }}>
                                  {res.delta > 0 ? "+" : ""}{fmt(res.delta)}
                                </span>
                                <span style={{ color: C.text }}>{res.name}</span>
                                <span style={{ color: C.muted }}>{res.service}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
            <tr>
              <td className="py-2.5 font-semibold text-xs" style={{ color: C.text }}>Total</td>
              <td className="py-2.5 text-right font-semibold" style={{ color: C.text }}>{data.resource_count}</td>
              <td className="py-2.5 text-right font-semibold" style={{ color: data.net_variance > 0 ? C.red : C.green }}>
                {data.net_variance > 0 ? "+" : ""}{fmt(data.net_variance)}
              </td>
              <td className="py-2.5 text-right font-semibold" style={{ color: C.muted }}>100%</td>
              <td></td>
            </tr>
          </tbody>
        </table>
      </Card>

      {/* Action items + Export side by side */}
      <div className="grid grid-cols-[1fr_1fr] gap-4">
        {data.action_items.length > 0 ? (
          <Card>
            <CardLabel>Action Items</CardLabel>
            <p className="text-[11px] mb-3" style={{ color: C.muted }}>Drift resources requiring follow-up</p>
            <div className="space-y-2">
              {data.action_items.map((item, i) => (
                <div key={i} className="cl-row-item flex items-center gap-2 rounded-lg px-3 py-2"
                  style={{ background: "#FAFAF8", border: `1px solid ${C.border}` }}>
                  <span className="text-xs font-medium shrink-0" style={{ color: C.red }}>
                    {item.delta > 0 ? "+" : ""}{fmt(item.delta)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs truncate" style={{ color: C.text }}>{item.resource_name}</p>
                    <p className="text-[10px]" style={{ color: C.muted }}>{item.action}</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ) : (
          <Card>
            <CardLabel>Action Items</CardLabel>
            <div className="flex items-center justify-center py-6">
              <p className="text-sm" style={{ color: C.green }}>No drift items — all resources are managed</p>
            </div>
          </Card>
        )}

        <Card className="flex flex-col">
          <CardLabel>Export</CardLabel>
          <p className="text-[11px] mb-3" style={{ color: C.muted }}>Download the close packet for finance review</p>
          <div className="space-y-2 mt-auto">
            <a href={api.glExportUrl(current)}
              className="cl-export block py-2.5 rounded-xl text-xs font-semibold text-center no-underline"
              style={{ background: C.accent, color: "#FFFFFF" }}>
              Journal Entry (CSV)
            </a>
            <a href={api.pdfExportUrl(current, prior)}
              className="cl-export block py-2.5 rounded-xl text-xs font-semibold text-center no-underline"
              style={{ background: C.text, color: "#FFFFFF" }}>
              Close Packet (PDF)
            </a>
          </div>
        </Card>
      </div>
    </Stagger>
  );
}

/* ═══ Screen 6: Engineering ═════════════════════════════════════════════════ */

function EngineeringScreen({ current, onData }: { current: string; onData?: (d: unknown) => void }) {
  const [data, setData] = useState<{
    managed_count: number; unmanaged_count: number; managed_cost: number; unmanaged_cost: number; total_cost: number;
    planned_count: number; planned_total: number; drift_count: number; drift_total: number;
    drift_resources: { resource_name: string; service: string; current_cost: number; delta: number; reason_code: string; team: string | null; iac_source: string }[];
    iac_sources: { source: string; count: number; cost: number }[];
    teams: { team: string; count: number; cost: number; managed: number; delta: number }[];
    total_resources: number;
  } | null>(null);

  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { setError(null); api.getEngineeringView(current).then(d => { setData(d); onData?.(d); }).catch(e => setError(e.message)); }, [current]);
  useEffect(load, [load]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <SkeletonScreen />;

  const coveragePct = data.total_resources > 0 ? (data.managed_count / data.total_resources) * 100 : 0;
  const costCoveragePct = data.total_cost > 0 ? (data.managed_cost / data.total_cost) * 100 : 0;

  return (
    <Stagger screenKey={6}>
      {/* KPI row */}
      <div className="grid grid-cols-4 gap-4 mb-4">
        <Card>
          <CardLabel>IaC Coverage</CardLabel>
          <BigNum>{coveragePct.toFixed(0)}%</BigNum>
          <CardSub>{data.managed_count} of {data.total_resources} resources</CardSub>
        </Card>
        <Card>
          <CardLabel>Managed Spend</CardLabel>
          <BigNum>{fmt(data.managed_cost)}</BigNum>
          <CardSub>{costCoveragePct.toFixed(0)}% of total cost</CardSub>
        </Card>
        <Card>
          <CardLabel>Drift Variance</CardLabel>
          <p className="text-2xl font-semibold" style={{ color: data.drift_total > 0 ? C.red : C.green }}>
            {fmt(data.drift_total)}
          </p>
          <CardSub>{data.drift_count} unmanaged resources</CardSub>
        </Card>
        <Card>
          <CardLabel>Planned Changes</CardLabel>
          <BigNum>{fmt(data.planned_total)}</BigNum>
          <CardSub>{data.planned_count} resources via IaC</CardSub>
        </Card>
      </div>

      {/* Coverage bar + IaC sources */}
      <div className="grid grid-cols-[1fr_280px] gap-4 mb-4">
        <Card>
          <CardLabel>Cost by IaC Status</CardLabel>
          <div className="mt-3">
            <div className="flex rounded-full h-5 overflow-hidden mb-2" style={{ background: "#F0EDE6" }}>
              {data.managed_cost > 0 && (
                <div style={{ width: `${costCoveragePct}%`, background: C.green }} title={`Managed: ${fmt(data.managed_cost)}`} />
              )}
              {data.unmanaged_cost > 0 && (
                <div style={{ width: `${100 - costCoveragePct}%`, background: C.red }} title={`Unmanaged: ${fmt(data.unmanaged_cost)}`} />
              )}
            </div>
            <div className="flex justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: C.green }} />
                <span style={{ color: C.text }}>Managed: {fmt(data.managed_cost)}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: C.red }} />
                <span style={{ color: C.text }}>Unmanaged: {fmt(data.unmanaged_cost)}</span>
              </div>
            </div>
          </div>

          {/* Team breakdown table */}
          {data.teams.length > 0 && (
            <div className="mt-5">
              <p className="text-xs font-medium mb-2" style={{ color: C.muted }}>By Team</p>
              <table className="cl-table w-full text-xs">
                <thead>
                  <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                    <th className="text-left py-1.5 font-medium" style={{ color: C.muted }}>Team</th>
                    <th className="text-right py-1.5 font-medium" style={{ color: C.muted }}>Spend</th>
                    <th className="text-right py-1.5 font-medium" style={{ color: C.muted }}>Delta</th>
                    <th className="text-right py-1.5 font-medium" style={{ color: C.muted }}>IaC</th>
                  </tr>
                </thead>
                <tbody>
                  {data.teams.map(t => (
                    <tr key={t.team} style={{ borderBottom: `1px solid ${C.border}` }}>
                      <td className="py-1.5" style={{ color: C.text }}>{t.team}</td>
                      <td className="py-1.5 text-right" style={{ color: C.accent }}>{fmt(t.cost)}</td>
                      <td className="py-1.5 text-right" style={{ color: t.delta > 0 ? C.red : t.delta < 0 ? C.green : C.muted }}>
                        {t.delta > 0 ? "+" : ""}{fmt(t.delta)}
                      </td>
                      <td className="py-1.5 text-right" style={{ color: t.managed === t.count ? C.green : C.red }}>
                        {t.managed}/{t.count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* IaC sources */}
        <Card>
          <CardLabel>IaC Sources</CardLabel>
          <div className="mt-3 space-y-2.5">
            {data.iac_sources.map(src => {
              const pct = data.total_resources > 0 ? (src.count / data.total_resources) * 100 : 0;
              const isNone = src.source === "none";
              return (
                <div key={src.source}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span style={{ color: isNone ? C.red : C.text }}>
                      {isNone ? "No IaC" : src.source.charAt(0).toUpperCase() + src.source.slice(1)}
                    </span>
                    <span style={{ color: C.muted }}>{src.count} ({pct.toFixed(0)}%)</span>
                  </div>
                  <div className="rounded-full h-2 overflow-hidden" style={{ background: "#F0EDE6" }}>
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: isNone ? C.red : C.green }} />
                  </div>
                  <p className="text-[11px] mt-0.5" style={{ color: C.muted }}>{fmt(src.cost)} in spend</p>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* Drift resources table */}
      {data.drift_resources.length > 0 && (
        <Card>
          <CardLabel>Drift Resources</CardLabel>
          <p className="text-[11px] mb-2" style={{ color: C.muted }}>Resources not managed by any IaC tool — candidates for terraform import</p>
          <div style={{ maxHeight: 300, overflowY: "auto" }}>
            <table className="cl-table w-full text-xs">
              <thead style={{ position: "sticky", top: 0, background: C.card }}>
                <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                  <th className="text-left py-2 font-medium" style={{ color: C.muted }}>Resource</th>
                  <th className="text-left py-2 font-medium" style={{ color: C.muted }}>Service</th>
                  <th className="text-left py-2 font-medium" style={{ color: C.muted }}>Team</th>
                  <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Spend</th>
                  <th className="text-right py-2 font-medium" style={{ color: C.muted }}>Delta</th>
                  <th className="text-left py-2 font-medium pl-3" style={{ color: C.muted }}>Reason</th>
                </tr>
              </thead>
              <tbody>
                {data.drift_resources.map((r, i) => (
                  <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}>
                    <td className="py-2 max-w-[180px] truncate" style={{ color: C.text }}>{r.resource_name}</td>
                    <td className="py-2" style={{ color: C.muted }}>{r.service}</td>
                    <td className="py-2" style={{ color: r.team ? C.text : C.muted }}>{r.team || "—"}</td>
                    <td className="py-2 text-right" style={{ color: C.text }}>{fmt(r.current_cost)}</td>
                    <td className="py-2 text-right font-medium" style={{ color: r.delta > 0 ? C.red : r.delta < 0 ? C.green : C.muted }}>
                      {r.delta > 0 ? "+" : ""}{fmt(r.delta)}
                    </td>
                    <td className="py-2 pl-3"><ReasonBadge code={r.reason_code} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </Stagger>
  );
}

/* ═══ Main App ══════════════════════════════════════════════════════════════ */

/* ═══ Cloudly Chat Panel ═══════════════════════════════════════════════════ */

/* Simple markdown renderer for Cloudly responses */
function CloudlyMarkdown({ text }: { text: string }) {
  // Split into lines, process bold, lists, and paragraphs
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let listItems: string[] = [];

  function flushList() {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="pl-4 space-y-0.5 my-1.5">
          {listItems.map((item, i) => <li key={i} className="list-disc">{renderInline(item)}</li>)}
        </ul>
      );
      listItems = [];
    }
  }

  function renderInline(s: string): React.ReactNode {
    // Bold: **text** and numbered highlights
    const parts = s.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={i} style={{ color: C.accent, fontWeight: 600 }}>{part.slice(2, -2)}</strong>;
      }
      return part;
    });
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith("- ") || line.startsWith("• ")) {
      listItems.push(line.slice(2));
    } else if (/^\d+\.\s/.test(line)) {
      listItems.push(line.replace(/^\d+\.\s/, ""));
    } else {
      flushList();
      if (line === "") {
        if (i > 0 && i < lines.length - 1) elements.push(<div key={`br-${i}`} className="h-2" />);
      } else {
        elements.push(<p key={`p-${i}`}>{renderInline(line)}</p>);
      }
    }
  }
  flushList();

  return <div className="space-y-1">{elements}</div>;
}

function CloudlyPanel({ open, onClose, screenName, screenData, onCopy }: {
  open: boolean; onClose: () => void; screenName: string; screenData: unknown; onCopy?: (msg: string) => void;
}) {
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 300);
  }, [open]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, loading]);

  async function send() {
    const msg = input.trim();
    if (!msg || loading) return;
    setInput("");
    setError(null);
    const updated = [...messages, { role: "user" as const, content: msg }];
    setMessages(updated);
    setLoading(true);
    try {
      const { reply } = await api.sendChat(msg, screenName, screenData, messages);
      setMessages([...updated, { role: "assistant", content: reply }]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to get response");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div className="fixed inset-0 z-40" style={{ background: "rgba(0,0,0,0.15)" }}
          onClick={onClose} />
      )}
      {/* Panel */}
      <div className="fixed top-0 right-0 h-full z-50 flex flex-col"
        style={{
          width: 400,
          background: C.card,
          borderLeft: `1px solid ${C.border}`,
          boxShadow: open ? "-4px 0 24px rgba(0,0,0,0.08)" : "none",
          transform: open ? "translateX(0)" : "translateX(100%)",
          transition: "transform 0.35s cubic-bezier(0.16,1,0.3,1)",
        }}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: `1px solid ${C.border}` }}>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full flex items-center justify-center"
              style={{ background: "rgba(201,99,58,0.1)" }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a7 7 0 0 1 7 7c0 2.4-1.2 4.5-3 5.7V17a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2v-2.3C6.2 13.5 5 11.4 5 9a7 7 0 0 1 7-7z"/>
                <line x1="10" y1="22" x2="14" y2="22"/>
              </svg>
            </div>
            <span className="text-sm font-semibold" style={{ color: C.text }}>Cloudly</span>
          </div>
          <button onClick={onClose} className="cursor-pointer p-1 rounded"
            style={{ background: "none", border: "none", color: C.muted, fontSize: 18 }}>
            &#x2715;
          </button>
        </div>

        {/* Context pill */}
        <div className="px-5 py-2">
          <span className="text-[11px] px-2.5 py-1 rounded-full"
            style={{ background: "rgba(201,99,58,0.08)", color: C.accent }}>
            Viewing: {screenName}
          </span>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-3 space-y-3"
          style={{ background: C.bg }}>
          {messages.length === 0 && !loading && (
            <div className="py-6">
              <p className="text-sm font-medium mb-1 text-center" style={{ color: C.text }}>Ask me anything about your data</p>
              <p className="text-xs text-center mb-4" style={{ color: C.muted }}>
                I can see the {screenName} screen and help you understand the analysis.
              </p>
              {(CLOUDLY_SUGGESTIONS[screenName] || []).map((q, i) => (
                <button key={i} onClick={() => { setInput(q); }}
                  className="cl-row-item w-full text-left text-xs px-3 py-2 mb-1.5 rounded-lg cursor-pointer"
                  style={{ background: C.card, border: `1px solid ${C.border}`, color: C.text }}>
                  {q}
                </button>
              ))}
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className="rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed max-w-[85%]"
                style={{
                  background: m.role === "user" ? C.accent : C.card,
                  color: m.role === "user" ? "#FFFFFF" : C.text,
                  border: m.role === "assistant" ? `1px solid ${C.border}` : "none",
                }}>
                {m.role === "assistant" ? <CloudlyMarkdown text={m.content} /> : m.content}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="rounded-xl px-3.5 py-2.5 text-[13px]"
                style={{ background: C.card, border: `1px solid ${C.border}`, color: C.muted }}>
                <span className="inline-flex gap-1">
                  <span className="animate-pulse">&#8226;</span>
                  <span className="animate-pulse" style={{ animationDelay: "0.2s" }}>&#8226;</span>
                  <span className="animate-pulse" style={{ animationDelay: "0.4s" }}>&#8226;</span>
                </span>
              </div>
            </div>
          )}
          {error && (
            <div className="text-xs text-center py-1" style={{ color: C.red }}>{error}</div>
          )}
        </div>

        {/* Input */}
        <div className="px-4 py-3" style={{ borderTop: `1px solid ${C.border}` }}>
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && send()}
              placeholder="Ask about your data..."
              className="flex-1 px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: `1px solid ${C.border}`, color: C.text, background: C.bg }}
            />
            <button onClick={send} disabled={!input.trim() || loading}
              className="px-3 py-2 rounded-lg text-xs font-medium cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: C.accent, color: "#FFFFFF", border: "none" }}>
              Send
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

/* ═══ Main App ══════════════════════════════════════════════════════════════ */

/* ═══ Helpers: Copy + Toast ════════════════════════════════════════════════ */

/* ═══ Screen 7: Trends ═════════════════════════════════════════════════════ */

function TrendsScreen({ onData }: { onData?: (d: unknown) => void }) {
  type TData = {
    totals: { period: string; cost: number }[];
    by_service: Record<string, { period: string; cost: number; resources: number }[]>;
    variances: { prior_period: string; current_period: string; net_change: number; total_variance: number; by_reason: Record<string, { delta: number; abs_delta: number; count: number }> }[];
    anomalies: { period: string; resource_name: string; service: string; delta: number; delta_pct: number; reason: string }[];
  };
  const [data, setData] = useState<TData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedService, setSelectedService] = useState<string | null>(null);
  const load = useCallback(() => { setError(null); api.getTrends().then(d => { setData(d); onData?.(d); }).catch(e => setError(e.message)); }, []);
  useEffect(load, [load]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <SkeletonScreen />;

  const services = Object.keys(data.by_service).sort((a, b) => {
    const aTotal = data.by_service[a].reduce((s, p) => s + p.cost, 0);
    const bTotal = data.by_service[b].reduce((s, p) => s + p.cost, 0);
    return bTotal - aTotal;
  });
  const topServices = services.slice(0, 8);

  // Build service line chart data
  const allPeriods = data.totals.map(t => t.period);
  const serviceChartData = allPeriods.map(period => {
    const row: Record<string, string | number> = { period: period.slice(5) }; // "03" from "2024-03"
    for (const svc of (selectedService ? [selectedService] : topServices.slice(0, 5))) {
      const entry = data.by_service[svc]?.find(e => e.period === period);
      row[svc] = entry?.cost || 0;
    }
    return row;
  });

  const svcColors = [C.accent, C.green, "#6B7FD7", C.accentLight, C.red, "#8B5CF6", "#14B8A6", "#F59E0B"];

  return (
    <Stagger screenKey={7}>
      {/* Total spend over time */}
      <Card className="mb-4">
        <CardLabel>Total Cloud Spend Over Time</CardLabel>
        <div className="mt-3" style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.totals.map(t => ({ ...t, label: monthLabel(t.period).split(" ")[0] }))} barSize={32}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.border} vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: C.muted }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: C.muted }} axisLine={false} tickLine={false} tickFormatter={v => fmt(v)} />
              <Tooltip formatter={(v) => fmt(Number(v))} contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${C.border}` }} />
              <Bar dataKey="cost" fill={C.accent} radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Service trends + Service selector */}
      <div className="grid grid-cols-[1fr_220px] gap-4 mb-4">
        <Card>
          <CardLabel>Cost by Service Over Time</CardLabel>
          <div className="mt-3" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={serviceChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.border} vertical={false} />
                <XAxis dataKey="period" tick={{ fontSize: 11, fill: C.muted }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: C.muted }} axisLine={false} tickLine={false} tickFormatter={v => fmt(v)} />
                <Tooltip formatter={(v) => fmt(Number(v))} contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${C.border}` }} />
                {(selectedService ? [selectedService] : topServices.slice(0, 5)).map((svc, i) => (
                  <Line key={svc} type="monotone" dataKey={svc} stroke={svcColors[i % svcColors.length]} strokeWidth={2} dot={{ r: 3 }} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardLabel>Services</CardLabel>
          <p className="text-[11px] mb-2" style={{ color: C.muted }}>Click to isolate</p>
          <div className="space-y-1">
            {topServices.map((svc, i) => {
              const isActive = selectedService === svc;
              return (
                <button key={svc} onClick={() => setSelectedService(isActive ? null : svc)}
                  className="w-full flex items-center gap-2 text-left text-[11px] px-2 py-1.5 rounded-lg cursor-pointer"
                  style={{ background: isActive ? "rgba(201,99,58,0.06)" : "transparent", border: "none", color: C.text }}>
                  <div className="w-2 h-2 rounded-full shrink-0" style={{ background: svcColors[i % svcColors.length] }} />
                  <span className="truncate flex-1">{svc}</span>
                </button>
              );
            })}
          </div>
        </Card>
      </div>

      {/* Variance over time + Anomalies */}
      <div className="grid grid-cols-2 gap-4">
        {data.variances.length > 0 && (
          <Card>
            <CardLabel>Month-over-Month Variance</CardLabel>
            <div className="mt-3" style={{ height: 180 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.variances.map(v => ({
                  period: v.current_period.slice(5),
                  net: v.net_change,
                }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.border} vertical={false} />
                  <XAxis dataKey="period" tick={{ fontSize: 11, fill: C.muted }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: C.muted }} axisLine={false} tickLine={false} tickFormatter={v => fmt(v)} />
                  <Tooltip formatter={(v) => fmt(Number(v))} contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${C.border}` }} />
                  <Bar dataKey="net" fill={C.accent} radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        )}

        {data.anomalies.length > 0 && (
          <Card>
            <CardLabel>Anomalies Detected</CardLabel>
            <p className="text-[11px] mb-2" style={{ color: C.muted }}>Resources with {">"}50% change and {">"}$500 impact</p>
            <div className="space-y-1.5" style={{ maxHeight: 200, overflowY: "auto" }}>
              {data.anomalies.map((a, i) => (
                <div key={i} className="cl-row-item flex items-center gap-2 rounded-lg px-2.5 py-1.5"
                  style={{ background: "#FAFAF8", border: `1px solid ${C.border}` }}>
                  <span className="text-xs font-medium shrink-0" style={{ color: a.delta > 0 ? C.red : C.green }}>
                    {a.delta > 0 ? "+" : ""}{fmt(a.delta)}
                  </span>
                  <span className="text-[11px] truncate flex-1" style={{ color: C.text }}>{a.resource_name}</span>
                  <span className="text-[10px] shrink-0" style={{ color: C.muted }}>{a.delta_pct > 0 ? "+" : ""}{a.delta_pct.toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </Stagger>
  );
}

/* ═══ Animated Mesh Background ═════════════════════════════════════════════ */

function MeshBackground() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        if (ref.current) {
          const y = window.scrollY;
          const children = ref.current.children;
          // Parallax — each aurora layer moves at different speed
          if (children[0]) (children[0] as HTMLElement).style.transform = `translateY(${y * 0.08}px) rotate(${y * 0.01}deg)`;
          if (children[1]) (children[1] as HTMLElement).style.transform = `translateY(${y * -0.05}px) rotate(${y * -0.008}deg)`;
        }
        ticking = false;
      });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div ref={ref} className="cl-mesh">
      <div className="cl-aurora" />
      <div className="cl-aurora-2" />
    </div>
  );
}

/* ═══ Context Ribbon ══════════════════════════════════════════════════════ */

function ContextRibbon({ screen, prior, current }: { screen: number; prior: string; current: string }) {
  const desc = SCREEN_DESC[screen];
  if (!desc || screen === 0) return null;
  return (
    <div className="flex items-center gap-3 mb-4 px-1">
      <div className="flex items-center gap-2">
        <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ background: "rgba(201,99,58,0.08)", color: C.accent }}>
          {monthLabel(prior)} → {monthLabel(current)}
        </span>
      </div>
      <span className="text-[11px]" style={{ color: C.muted }}>{desc}</span>
    </div>
  );
}

/* ═══ Main App ══════════════════════════════════════════════════════════════ */

export default function Home() {
  const [screen, setScreen] = useState(-1); // -1 = landing
  const [prior, setPrior] = useState("");
  const [current, setCurrent] = useState("");
  const [uploadFiles, setUploadFiles] = useState<UploadFiles>({
    billingFiles: [], terraform: null,
  });
  const [allPeriods, setAllPeriods] = useState<string[]>([]);
  const pipelineDone = prior !== "" && current !== "";
  const [cloudlyOpen, setCloudlyOpen] = useState(false);
  const [footerModal, setFooterModal] = useState<string | null>(null);
  const screenDataRef = useRef<Record<string, unknown>>({});
  const screenNames = SCREEN_NAMES;
  const toast = useToast();

  const handleDone = useCallback((p: string, c: string, all?: string[]) => {
    setPrior(p);
    setCurrent(c);
    if (all) setAllPeriods(all);
    setScreen(1);
  }, []);

  // Keyboard shortcuts: 1-7 for tabs, Esc to close panels
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      // Don't intercept when typing in inputs
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "Escape") {
        setCloudlyOpen(false);
        setFooterModal(null);
      }
      if (pipelineDone && e.key >= "1" && e.key <= "8") {
        setScreen(parseInt(e.key) - 1);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [pipelineDone]);

  const footer = (
    <footer className="mt-16 pb-6 relative" style={{ borderTop: `1px solid ${C.border}`, zIndex: 1 }}>
      <div className="max-w-[1200px] mx-auto px-6 pt-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg width="14" height="11" viewBox="0 0 120 85" fill="none">
              <path
                d="M30 65C18 65 10 57 10 47c0-9 6-16 14-18 0-14 12-24 26-24 11 0 20 6 24 15 2-1 5-2 8-2 10 0 18 8 18 18h2c8 0 14 6 14 14s-6 14-14 14H30z"
                stroke={C.muted} strokeWidth="4" fill="none"
              />
            </svg>
            <span className="text-[11px]" style={{ color: C.muted }}>
              &copy; {new Date().getFullYear()} CloudLedger. All rights reserved.
            </span>
          </div>
          <div className="flex gap-5">
            <button onClick={() => setFooterModal("terms")} className="cl-footer-link text-[11px] cursor-pointer"
              style={{ color: C.muted, background: "none", border: "none", textDecoration: "underline", textUnderlineOffset: 2 }}>
              Terms of Use
            </button>
            <button onClick={() => setFooterModal("privacy")} className="cl-footer-link text-[11px] cursor-pointer"
              style={{ color: C.muted, background: "none", border: "none", textDecoration: "underline", textUnderlineOffset: 2 }}>
              Privacy Policy
            </button>
            <button onClick={() => setFooterModal("security")} className="cl-footer-link text-[11px] cursor-pointer"
              style={{ color: C.muted, background: "none", border: "none", textDecoration: "underline", textUnderlineOffset: 2 }}>
              Security
            </button>
          </div>
        </div>
      </div>
    </footer>
  );

  const modalContent: Record<string, { title: string; body: string }> = {
    terms: {
      title: "Terms of Use",
      body: `Last updated: April 2026

1. Acceptance of Terms
By accessing or using CloudLedger, you agree to be bound by these Terms of Use. If you do not agree, do not use the service.

2. Service Description
CloudLedger provides cloud billing variance analysis tools. The service processes billing data you upload to generate variance reports, root cause analysis, and close packets.

3. Data Ownership
You retain all rights to your data. CloudLedger does not claim ownership of any billing data, Terraform state files, or other materials you upload. Your data is processed solely to provide the analysis you request.

4. Acceptable Use
You agree not to: (a) upload data you do not have authorization to process; (b) use the service to violate any applicable law or regulation; (c) attempt to reverse-engineer, decompile, or disassemble the service; (d) interfere with or disrupt the service infrastructure.

5. Data Processing
Uploaded billing data is processed in-memory and stored in your local database instance. CloudLedger does not transmit your billing data to third parties, except when you explicitly use the AI assistant feature (Cloudly), which sends screen-level context to Anthropic's API.

6. Disclaimer of Warranties
The service is provided "as is" without warranties of any kind. CloudLedger does not guarantee the accuracy of variance calculations or reason code classifications. You are responsible for verifying analysis results before using them for financial reporting.

7. Limitation of Liability
CloudLedger shall not be liable for any indirect, incidental, special, or consequential damages arising from your use of the service, including but not limited to errors in financial reporting based on CloudLedger output.

8. Changes to Terms
We reserve the right to modify these terms at any time. Continued use of the service constitutes acceptance of modified terms.`,
    },
    privacy: {
      title: "Privacy Policy",
      body: `Last updated: April 2026

1. Information We Process
CloudLedger processes cloud billing CSVs, Terraform state files, and infrastructure metadata that you upload. This data is stored locally in your PostgreSQL database and is not transmitted to external servers except as noted below.

2. AI Assistant (Cloudly)
When you use the Cloudly AI assistant, the data currently displayed on your screen is sent to Anthropic's Claude API to generate responses. This data is subject to Anthropic's usage policies. Conversation history is stored only in your browser session and is not persisted.

3. No Tracking or Analytics
CloudLedger does not use cookies, analytics trackers, or any third-party tracking services. No usage data is collected or transmitted.

4. Data Retention
Your data remains in your local database until you delete it. CloudLedger does not maintain copies of your data on external servers.

5. Data Security
All data processing occurs locally. Database connections use the credentials you configure. We recommend using strong passwords and restricting database access to authorized users.

6. Contact
For privacy-related inquiries, contact your CloudLedger administrator.`,
    },
    security: {
      title: "Security",
      body: `Last updated: April 2026

1. Architecture
CloudLedger runs entirely on your infrastructure. The backend API server, database, and frontend are all deployed locally. No billing data leaves your environment except when using the Cloudly AI feature.

2. Data in Transit
The frontend communicates with the backend over your local network. For production deployments, we recommend configuring TLS/HTTPS.

3. Data at Rest
Billing data is stored in PostgreSQL using the credentials you configure in your .env file. We recommend encrypting your database volume and using role-based access controls.

4. Authentication
CloudLedger does not currently include built-in authentication. For multi-user deployments, we recommend placing the application behind your organization's identity provider (SSO, OAuth, etc.).

5. API Keys
The Anthropic API key used by Cloudly is stored in your .env file. This key is never exposed to the frontend — all AI requests are proxied through the backend.

6. Dependency Security
CloudLedger uses pinned dependencies. We recommend regularly updating packages and auditing for known vulnerabilities.

7. Responsible Disclosure
If you discover a security vulnerability, please report it to your CloudLedger administrator immediately.`,
    },
  };

  // Landing page — no nav bar, standalone
  if (screen === -1) {
    return (
      <div className="min-h-screen px-6 py-4 flex flex-col" style={{ background: C.bg }}>
        <MeshBackground />
        <div className="max-w-[960px] mx-auto flex-1 w-full relative" style={{ zIndex: 1 }}>
          {/* Minimal header */}
          <div className="flex items-center gap-2 py-3 mb-4">
            <svg width="20" height="16" viewBox="0 0 120 85" fill="none">
              <path
                d="M30 65C18 65 10 57 10 47c0-9 6-16 14-18 0-14 12-24 26-24 11 0 20 6 24 15 2-1 5-2 8-2 10 0 18 8 18 18h2c8 0 14 6 14 14s-6 14-14 14H30z"
                stroke={C.accent} strokeWidth="4" fill="none"
              />
            </svg>
            <span className="text-sm font-semibold" style={{ color: C.accent }}>CloudLedger</span>
          </div>
          <FadeIn screenKey={-1}>
            <LandingPage onStart={() => setScreen(0)} />
          </FadeIn>
        </div>
        {footer}
        {footerModal && modalContent[footerModal] && (
          <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.3)" }}
            onClick={() => setFooterModal(null)}>
            <div className="rounded-xl p-6 max-w-[600px] w-full max-h-[80vh] overflow-y-auto"
              style={{ background: C.card, border: `1px solid ${C.border}`, boxShadow: "0 8px 32px rgba(0,0,0,0.12)" }}
              onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-base font-semibold" style={{ color: C.text }}>{modalContent[footerModal].title}</h3>
                <button onClick={() => setFooterModal(null)} className="cursor-pointer p-1"
                  style={{ background: "none", border: "none", color: C.muted, fontSize: 18 }}>&#x2715;</button>
              </div>
              <div className="text-xs leading-relaxed whitespace-pre-wrap" style={{ color: C.text }}>
                {modalContent[footerModal].body}
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="min-h-screen px-6 py-4 flex flex-col" style={{ background: C.bg }}>
      <MeshBackground />
      <div className="max-w-[1200px] mx-auto flex-1 w-full relative" style={{ zIndex: 1 }}>
        <TopNav screen={screen} onNav={setScreen} pipelineDone={pipelineDone} onCloudly={() => setCloudlyOpen(true)} />
        {pipelineDone && <ContextRibbon screen={screen} prior={prior} current={current} />}

        <FadeIn screenKey={screen}>
          {screen === 0 && <UploadScreen files={uploadFiles} setFiles={setUploadFiles} onDone={handleDone} />}
          {screen === 1 && <OverviewScreen prior={prior} current={current} onData={d => { screenDataRef.current.Overview = d; }} />}
          {screen === 2 && <IngestionScreen current={current} onData={d => { screenDataRef.current.Ingestion = d; }} />}
          {screen === 3 && <VarianceScreen current={current} onData={d => { screenDataRef.current.Variance = d; }} />}
          {screen === 4 && <RootCausesScreen current={current} onData={d => { screenDataRef.current["Root Causes"] = d; }} />}
          {screen === 5 && <ClosePacketScreen current={current} prior={prior} onData={d => { screenDataRef.current["Close Packet"] = d; }} />}
          {screen === 6 && <EngineeringScreen current={current} onData={d => { screenDataRef.current.Engineering = d; }} />}
          {screen === 7 && <TrendsScreen onData={d => { screenDataRef.current.Trends = d; }} />}
        </FadeIn>
      </div>

      {footer}

      {footerModal && modalContent[footerModal] && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.3)" }}
          onClick={() => setFooterModal(null)}>
          <div className="rounded-xl p-6 max-w-[600px] w-full max-h-[80vh] overflow-y-auto"
            style={{ background: C.card, border: `1px solid ${C.border}`, boxShadow: "0 8px 32px rgba(0,0,0,0.12)" }}
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold" style={{ color: C.text }}>{modalContent[footerModal].title}</h3>
              <button onClick={() => setFooterModal(null)} className="cursor-pointer p-1"
                style={{ background: "none", border: "none", color: C.muted, fontSize: 18 }}>&#x2715;</button>
            </div>
            <div className="text-xs leading-relaxed whitespace-pre-wrap" style={{ color: C.text }}>
              {modalContent[footerModal].body}
            </div>
          </div>
        </div>
      )}

      <CloudlyPanel
        open={cloudlyOpen}
        onClose={() => setCloudlyOpen(false)}
        screenName={screenNames[screen] || "Upload"}
        screenData={{ current_screen: screenNames[screen] || "Upload", all_screens: screenDataRef.current }}
        onCopy={toast.show}
      />
      {toast.el}
    </div>
  );
}
