"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { C } from "@/lib/constants";

/* ── Animation wrappers ─────────────────────────────────────────────── */

export function FadeIn({ screenKey, children }: { screenKey: number; children: React.ReactNode }) {
  const [visible, setVisible] = useState(true);
  const prevKey = useRef(screenKey);

  useEffect(() => {
    if (prevKey.current !== screenKey) {
      prevKey.current = screenKey;
      setVisible(false);
      const t = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(t);
    }
  }, [screenKey]);

  return (
    <div style={{ opacity: visible ? 1 : 0, transition: "opacity 0.2s ease" }}>
      {children}
    </div>
  );
}

export function Stagger({ screenKey, children }: { screenKey: number; children: React.ReactNode }) {
  const [tick, setTick] = useState(0);
  useEffect(() => { setTick(t => t + 1); }, [screenKey]);

  const items = Array.isArray(children) ? children.flat().filter(Boolean) : [children];
  return (
    <>
      {items.map((child, i) => (
        <StaggerItem key={`${tick}-${i}`} index={i}>{child}</StaggerItem>
      ))}
    </>
  );
}

function StaggerItem({ index, children }: { index: number; children: React.ReactNode }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), index * 70);
    return () => clearTimeout(t);
  }, [index]);

  return (
    <div style={{
      opacity: visible ? 1 : 0,
      transform: visible ? "translateY(0)" : "translateY(16px)",
      transition: "opacity 0.45s cubic-bezier(0.16,1,0.3,1), transform 0.45s cubic-bezier(0.16,1,0.3,1)",
    }}>
      {children}
    </div>
  );
}

/* ── Card system ────────────────────────────────────────────────────── */

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`cl-card rounded-2xl p-5 ${className}`}
      style={{
        background: "rgba(255,255,255,0.92)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        border: `1px solid ${C.border}`,
        boxShadow: "0 1px 3px rgba(0,0,0,0.03), 0 0 0 1px rgba(0,0,0,0.01)",
      }}>
      {children}
    </div>
  );
}

export function CardLabel({ children }: { children: React.ReactNode }) {
  return <p className="text-sm font-medium mb-1" style={{ color: C.text }}>{children}</p>;
}

export function CardSub({ children }: { children: React.ReactNode }) {
  return <p className="text-xs" style={{ color: C.muted }}>{children}</p>;
}

export function BigNum({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div>
      <p className="text-3xl font-semibold tracking-tight" style={{ color: C.accent, fontVariantNumeric: "tabular-nums" }}>{children}</p>
      {sub && <CardSub>{sub}</CardSub>}
    </div>
  );
}

export function Change({ value, label }: { value: number; label?: string }) {
  const positive = value >= 0;
  return (
    <p className="text-xs font-medium mt-1" style={{ color: positive ? C.green : C.red }}>
      {positive ? "↑" : "↓"} {positive ? "+" : ""}{value.toFixed(1)}%
      {label && <span style={{ color: C.muted, marginLeft: 4 }}>{label}</span>}
    </p>
  );
}

/* ── Loading & error states ─────────────────────────────────────────── */

export function Skeleton({ className = "", style = {} }: { className?: string; style?: React.CSSProperties }) {
  return (
    <div className={`rounded ${className}`}
      style={{ background: `linear-gradient(90deg, ${C.border} 25%, #F0EDE6 50%, ${C.border} 75%)`,
        backgroundSize: "200% 100%", animation: "shimmer 1.5s infinite", ...style }} />
  );
}

export function SkeletonScreen() {
  return (
    <Stagger screenKey={-99}>
      <div className="grid grid-cols-4 gap-4 mb-4">
        {[0,1,2,3].map(i => (
          <Card key={i}><Skeleton className="h-4 w-24 mb-3" /><Skeleton className="h-8 w-20 mb-1" /><Skeleton className="h-3 w-16" /></Card>
        ))}
      </div>
      <Card><Skeleton className="h-4 w-32 mb-4" /><Skeleton className="h-40 w-full" /></Card>
    </Stagger>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Card className="text-center py-10">
      <p className="text-sm font-medium mb-1" style={{ color: C.red }}>Something went wrong</p>
      <p className="text-xs mb-4" style={{ color: C.muted }}>{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="cl-btn px-4 py-1.5 rounded-lg text-xs font-medium cursor-pointer"
          style={{ background: C.accent, color: "#FFFFFF", border: "none" }}>
          Try again
        </button>
      )}
    </Card>
  );
}

/* ── Reason badge ───────────────────────────────────────────────────── */

export function ReasonBadge({ code }: { code: string }) {
  const colors: Record<string, { bg: string; fg: string }> = {
    planned: { bg: "rgba(47,168,79,0.1)", fg: C.green },
    new_resource: { bg: "rgba(47,168,79,0.1)", fg: C.green },
    removed_resource: { bg: "rgba(153,153,153,0.1)", fg: C.muted },
    steady_state: { bg: "rgba(153,153,153,0.08)", fg: C.muted },
    usage_growth: { bg: "rgba(201,99,58,0.1)", fg: C.accent },
    price_change: { bg: "rgba(201,99,58,0.1)", fg: C.accent },
  };
  const style = colors[code] || { bg: "rgba(217,68,68,0.1)", fg: C.red };
  const label = code.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  return (
    <span className="cl-badge text-[10px] font-medium px-1.5 py-0.5 rounded inline-block"
      style={{ background: style.bg, color: style.fg, whiteSpace: "nowrap" }}>
      {label}
    </span>
  );
}

/* ── Toast hook ─────────────────────────────────────────────────────── */

export function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  const show = useCallback((text: string) => {
    setMsg(text);
    setTimeout(() => setMsg(null), 2000);
  }, []);
  const el = msg ? (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-xl text-xs font-medium"
      style={{ background: C.text, color: "#FFFFFF", boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
        animation: "fadeSlideIn 0.3s cubic-bezier(0.16,1,0.3,1)" }}>
      {msg}
    </div>
  ) : null;
  return { show, el };
}
