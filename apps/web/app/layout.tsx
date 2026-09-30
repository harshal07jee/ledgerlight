import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ledgerlight — Diligence Readiness Platform",
  description: "Find your deal-breakers before an investor does. Rules-based, explainable readiness scoring and remediation roadmap.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col justify-between selection:bg-accent selection:text-white">
        {/* Editorial Top Navigation */}
        <header className="border-b border-border bg-paper/90 backdrop-blur sticky top-0 z-50">
          <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <span className="font-serif text-2xl font-bold tracking-tight text-ink">
                Ledgerlight
              </span>
              <span className="text-xs uppercase tracking-widest font-mono text-ink-muted bg-surface px-2 py-0.5 border border-border rounded-sm">
                Audit Tool
              </span>
            </div>

            <nav className="flex items-center space-x-6 text-sm font-medium text-ink-muted">
              <a href="#dimensions" className="hover:text-ink transition-colors">11 Dimensions</a>
              <a href="#workflow" className="hover:text-ink transition-colors">How It Works</a>
              <a href="#sources" className="hover:text-ink transition-colors">Regulatory Sources</a>
              <a
                href="/admin"
                className="text-xs font-mono px-3 py-1.5 rounded-sm border border-border bg-surface hover:border-ink transition-colors text-ink"
              >
                Question Bank
              </a>
              <a
                href="#get-started"
                className="px-4 py-1.5 rounded-md bg-accent text-white font-medium hover:bg-accent-hover transition-colors shadow-sm text-xs"
              >
                Start Assessment
              </a>
            </nav>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1">
          {children}
        </main>

        {/* Editorial Footer with Mandatory PRD Disclaimer */}
        <footer className="border-t border-border bg-surface py-12 text-sm text-ink-muted mt-20">
          <div className="max-w-6xl mx-auto px-6 space-y-6">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
              <div>
                <p className="font-serif font-bold text-lg text-ink">Ledgerlight</p>
                <p className="text-xs mt-1 text-ink-muted">
                  Confidence-gated diligence readiness and deterministic risk scoring.
                </p>
              </div>
              <div className="flex gap-6 text-xs font-mono">
                <span>NVCA 2025 Model Ready</span>
                <span>•</span>
                <span>ILPA DDQ 2.0 Grounded</span>
                <span>•</span>
                <span>US Jurisdiction</span>
              </div>
            </div>

            <div className="pt-6 border-t border-border/60">
              <p className="text-xs leading-relaxed text-ink-muted max-w-4xl">
                <strong>Disclaimer:</strong> This is a readiness assessment based on the information provided. It is not legal, financial, or investment advice and does not predict transaction outcomes. Extractive answers are linked to source text and low-confidence answers are routed for human review.
              </p>
              <p className="text-xs text-ink-muted/80 mt-3 font-mono">
                © {new Date().getFullYear()} Ledgerlight Systems Inc. All rights reserved.
              </p>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
