"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { NavigationMenu } from "@/components/ui-21st/navigation-menu";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SubSectorOption {
  value: string;
  label: string;
}

const INDUSTRY_SUB_SECTORS: Record<string, SubSectorOption[]> = {
  HEALTHCARE: [
    { value: "Medical_Devices", label: "Medical Devices (FDA Class I / II / III)" },
    { value: "Digital_Health", label: "Digital Health / SaMD / Telehealth" },
    { value: "Biotechnology", label: "Biotechnology / Therapeutics" },
    { value: "Pharmaceuticals", label: "Pharmaceuticals & Clinical Pipeline" },
    { value: "ALL", label: "General Healthcare Services" },
  ],
  FINTECH: [
    { value: "Payments/MSB", label: "Payments, Money Transmission & MSB" },
    { value: "Lending", label: "Lending & Credit Origination (TILA / Usury)" },
    { value: "Digital Assets", label: "Digital Assets & Crypto Custody" },
    { value: "WealthTech/RIA", label: "WealthTech & Registered Investment Advisory" },
    { value: "ALL", label: "General Financial Technology" },
  ],
  SOFTWARE: [
    { value: "B2B Enterprise SaaS", label: "B2B Enterprise SaaS & Cloud Infrastructure" },
    { value: "AI Infrastructure", label: "AI / Machine Learning Platform" },
    { value: "ALL", label: "General Software & Developer Tools" },
  ],
  MANUFACTURING: [
    { value: "Contract Manufacturer", label: "Contract Manufacturer (High-Mix / Low-Volume)" },
    { value: "Heavy Industrial Equipment", label: "Heavy Industrial, Defense & Hardware" },
    { value: "Chemicals and Materials", label: "Chemicals, Advanced Materials & Plastics" },
    { value: "ALL", label: "General Manufacturing & Fabrication" },
  ],
  ENERGY: [
    { value: "Solar & Wind Generation", label: "Utility-Scale Solar & Wind Generation" },
    { value: "Battery & Energy Storage", label: "Battery & Energy Storage Systems (BESS)" },
    { value: "Grid Infrastructure / OT", label: "Grid Infrastructure & Industrial OT" },
    { value: "ALL", label: "CleanTech & Decarbonization" },
  ],
};

const STAGES = [
  { value: "Startup", label: "Early / Seed Stage", desc: "Seed to Series A; initial commercialization" },
  { value: "Growth", label: "Growth Stage", desc: "Series B to Pre-IPO; scaling revenue and headcount" },
  { value: "Established", label: "Established Enterprise", desc: "Predictable profitability, mature corporate structure" },
  { value: "Mature", label: "Mature / Turnaround", desc: "Complex corporate entities, carve-outs, or buyout target" },
];

const TRANSACTION_TYPES = [
  { value: "VC_GROWTH_FINANCING", label: "VC Growth Financing", desc: "Series A–C diligence; heavy focus on IP ownership and sales quality" },
  { value: "M&A_SELL_SIDE", label: "M&A Sell-Side", desc: "Acquisition audit; rigorous scrutiny of contracts, assignability, and liabilities" },
  { value: "IPO_PREP", label: "IPO Preparation", desc: "Public market readiness; SOX controls, board governance, and SEC disclosures" },
  { value: "DEBT_FINANCING", label: "Debt Financing", desc: "Lender diligence; cash burn coverage, debt covenants, and asset liens" },
];

export default function OnboardingPage() {
  const router = useRouter();

  // Step 1: User & Org
  const [fullName, setFullName] = useState("Jane Founder");
  const [email, setEmail] = useState("founder@company.com");
  const [password, setPassword] = useState("Password123!");
  const [companyName, setCompanyName] = useState("Acme Technology");

  // Step 2: Diligence Context
  const [industry, setIndustry] = useState("SOFTWARE");
  const [subSector, setSubSector] = useState("B2B Enterprise SaaS");
  const [stage, setStage] = useState("Growth");
  const [transactionType, setTransactionType] = useState("VC_GROWTH_FINANCING");

  const [step, setStep] = useState<1 | 2>(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleIndustryChange = (newInd: string) => {
    setIndustry(newInd);
    const availableSubs = INDUSTRY_SUB_SECTORS[newInd] || [];
    setSubSector(availableSubs[0]?.value || "ALL");
  };

  const handleStep1Submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName || !email || !companyName) {
      setErrorMsg("Please fill out all identity fields.");
      return;
    }
    setErrorMsg(null);
    setStep(2);
  };

  const handleFinalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      // 1. Sign up or log in
      const signupRes = await fetch(`${API_BASE}/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: fullName,
          email: email,
          password: password,
          company_name: companyName,
        }),
      });

      const signupData = await signupRes.json();
      if (!signupRes.ok) {
        throw new Error(signupData.detail || "Sign-up failed");
      }

      const token = signupData.access_token;
      const orgId = signupData.organization?.id;
      if (typeof window !== "undefined") {
        localStorage.setItem("ledgerlight_token", token);
        localStorage.setItem("ledgerlight_user", JSON.stringify(signupData.user));
      }

      // 2. Create Assessment
      const assessRes = await fetch(`${API_BASE}/orgs/${orgId}/assessments`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: `${companyName} Diligence Assessment`,
          industry: industry,
          sub_sector: subSector,
          stage: stage,
          transaction_type: transactionType,
          geography: ["USA"],
        }),
      });

      const assessData = await assessRes.json();
      if (!assessRes.ok) {
        throw new Error(assessData.detail || "Failed to initialize assessment workspace.");
      }

      // 3. Navigate to Questionnaire
      const assessmentId = assessData.assessment.id;
      router.push(`/assessment/${assessmentId}`);
    } catch (err: any) {
      setErrorMsg(err.message || "An unexpected error occurred during setup.");
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F6F3EC] text-[#16181D]">
      {/* 21st.dev Slot: @shadcn/navigation-menu - Clean editorial header */}
      <NavigationMenu
        rightElement={
          <span className="font-mono text-xs text-[#5F6470]">
            Step {step} of 2
          </span>
        }
      />

      <main className="mx-auto max-w-3xl px-4 py-12 sm:px-6 lg:px-8">
        {/* Editorial Title Banner */}
        <div className="mb-8 border-b border-[#E2DDD2] pb-6">
          <span className="font-mono text-xs font-semibold uppercase tracking-wider text-[#1F4D3F]">
            Assessment Initialization
          </span>
          <h1 className="mt-2 font-serif text-3xl font-semibold tracking-tight text-[#16181D] sm:text-4xl">
            {step === 1 ? "Organization Setup" : "Diligence Context & Scope"}
          </h1>
          <p className="mt-2 text-sm text-[#5F6470] leading-relaxed">
            {step === 1
              ? "Create your workspace to run institutional-grade audit checks before external investors open your data room."
              : "Specify your industry vertical and transaction type to activate the rules-based question bank and prune non-applicable inquiries."}
          </p>
        </div>

        {errorMsg && (
          <div className="mb-6 rounded-lg border border-[#B4382F]/30 bg-[#B4382F]/5 p-4 text-sm text-[#B4382F]">
            {errorMsg}
          </div>
        )}

        {step === 1 ? (
          /* STEP 1: IDENTITY & ORG */
          <form
            onSubmit={handleStep1Submit}
            className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-8 shadow-xs"
          >
            <h2 className="font-serif text-lg font-semibold text-[#16181D]">
              1. Principal Credentials & Entity Name
            </h2>
            <p className="mt-1 text-xs text-[#5F6470]">
              Audits are sealed to your tenant. No document text or answers are shared with third parties.
            </p>

            <div className="mt-6 space-y-5">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-[#5F6470]">
                  Full Name
                </label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="e.g. Jane Founder"
                  className="mt-1.5 block w-full rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/30 px-3.5 py-2.5 text-sm text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden focus:ring-1 focus:ring-[#1F4D3F]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-[#5F6470]">
                  Corporate Work Email
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="founder@company.com"
                  className="mt-1.5 block w-full rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/30 px-3.5 py-2.5 text-sm text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden focus:ring-1 focus:ring-[#1F4D3F]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-[#5F6470]">
                  Password
                </label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="mt-1.5 block w-full rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/30 px-3.5 py-2.5 text-sm text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden focus:ring-1 focus:ring-[#1F4D3F]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-[#5F6470]">
                  Company / Organization Legal Name
                </label>
                <input
                  type="text"
                  required
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="Acme Technology Holdings, Inc."
                  className="mt-1.5 block w-full rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/30 px-3.5 py-2.5 text-sm text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden focus:ring-1 focus:ring-[#1F4D3F]"
                />
              </div>
            </div>

            <div className="mt-8 flex justify-end border-t border-[#E2DDD2] pt-6">
              <button
                type="submit"
                className="inline-flex items-center gap-2 rounded-lg bg-[#1F4D3F] px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#17392F]"
              >
                Continue to Diligence Profile
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </button>
            </div>
          </form>
        ) : (
          /* STEP 2: DILIGENCE CONTEXT */
          <form
            onSubmit={handleFinalSubmit}
            className="space-y-6 rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-8 shadow-xs"
          >
            <div>
              <h2 className="font-serif text-lg font-semibold text-[#16181D]">
                2. Industry Vertical & Sector Branch
              </h2>
              <p className="mt-1 text-xs text-[#5F6470]">
                Select your primary operating industry. This dynamically filters the question bank to relevant regulatory, technical, and operational checks.
              </p>

              {/* Industry Grid */}
              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {[
                  { id: "SOFTWARE", name: "Software (SaaS)", desc: "Copyleft open source, SLA liability caps, AI data rights, SOC 2" },
                  { id: "HEALTHCARE", name: "HealthCare & Life Sciences", desc: "FDA 510(k)/PMA, QMSR/ISO 13485, HITRUST, medical device cybersecurity" },
                  { id: "FINTECH", name: "FinTech & Financial Services", desc: "MSB/FinCEN, CFPB 1033, PCI-DSS v4.0, FBO reconciliation" },
                  { id: "ENERGY", name: "Energy & CleanTech", desc: "FERC Order 2023, IRA tax credits, Phase I ESA, NERC CIP OT" },
                  { id: "MANUFACTURING", name: "Manufacturing & Industrial", desc: "EPA PFAS lookback, ISO 9001 SPC, OSHA TRIR, ITAR/EAR" },
                ].map((ind) => (
                  <button
                    key={ind.id}
                    type="button"
                    onClick={() => handleIndustryChange(ind.id)}
                    className={`flex flex-col text-left rounded-lg border p-4 transition-all ${
                      industry === ind.id
                        ? "border-[#1F4D3F] bg-[#E8F0EC]/60 ring-1 ring-[#1F4D3F]"
                        : "border-[#E2DDD2] bg-[#FFFFFF] hover:border-[#1F4D3F]/50"
                    }`}
                  >
                    <span className="font-semibold text-sm text-[#16181D]">{ind.name}</span>
                    <span className="mt-1 text-xs text-[#5F6470]">{ind.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Sub-Sector */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-[#5F6470]">
                Sub-Sector Classification
              </label>
              <select
                value={subSector}
                onChange={(e) => setSubSector(e.target.value)}
                className="mt-1.5 block w-full rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/30 px-3.5 py-2.5 text-sm text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden focus:ring-1 focus:ring-[#1F4D3F]"
              >
                {(INDUSTRY_SUB_SECTORS[industry] || []).map((sub) => (
                  <option key={sub.value} value={sub.value}>
                    {sub.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Company Stage */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-[#5F6470]">
                Operating Stage
              </label>
              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {STAGES.map((s) => (
                  <label
                    key={s.value}
                    className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                      stage === s.value
                        ? "border-[#1F4D3F] bg-[#E8F0EC]/60"
                        : "border-[#E2DDD2] bg-[#FFFFFF] hover:bg-[#F6F3EC]/50"
                    }`}
                  >
                    <input
                      type="radio"
                      name="stage"
                      value={s.value}
                      checked={stage === s.value}
                      onChange={() => setStage(s.value)}
                      className="mt-1 text-[#1F4D3F] focus:ring-[#1F4D3F]"
                    />
                    <div>
                      <div className="text-xs font-medium text-[#16181D]">{s.label}</div>
                      <div className="text-[11px] text-[#5F6470]">{s.desc}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* Transaction Type */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-[#5F6470]">
                Target Transaction Objective
              </label>
              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {TRANSACTION_TYPES.map((t) => (
                  <label
                    key={t.value}
                    className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                      transactionType === t.value
                        ? "border-[#1F4D3F] bg-[#E8F0EC]/60"
                        : "border-[#E2DDD2] bg-[#FFFFFF] hover:bg-[#F6F3EC]/50"
                    }`}
                  >
                    <input
                      type="radio"
                      name="transactionType"
                      value={t.value}
                      checked={transactionType === t.value}
                      onChange={() => setTransactionType(t.value)}
                      className="mt-1 text-[#1F4D3F] focus:ring-[#1F4D3F]"
                    />
                    <div>
                      <div className="text-xs font-medium text-[#16181D]">{t.label}</div>
                      <div className="text-[11px] text-[#5F6470]">{t.desc}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="mt-8 flex items-center justify-between border-t border-[#E2DDD2] pt-6">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-4 py-2 text-sm font-medium text-[#16181D] hover:bg-[#F6F3EC] transition-colors"
              >
                Back
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="inline-flex items-center gap-2 rounded-lg bg-[#1F4D3F] px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#17392F] disabled:opacity-60"
              >
                {isSubmitting ? "Initializing Audit..." : "Open Diligence Questionnaire"}
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </button>
            </div>
          </form>
        )}
      </main>
    </div>
  );
}
