# Diligence Question Bank Extraction Coverage & CUAD Routing Report

> **Generated for:** Ledgerlight Diligence Readiness Platform (PRD Section 7.4 & M1 Cleanup)
> **Total Questions Analyzed:** 209 (Branch: 121, Core: 88)

> [!NOTE]
> **Important Disclaimer on CUAD Category Mapping:**
> The CUAD categories assigned below are **design-time routing labels** used to direct extracted document clauses to specialized extractive QA models. They represent intended pipeline targets, **NOT** empirically measured model extraction accuracy or benchmark performance.

## 1. Executive Summary

- **Auto-Extractable Proposals:** **125** questions (**59.8%**)
- **Manual Entry / Self-Attested Required:** **84** questions (**40.2%**)

> Per PRD Section 7.4, the manual share in MVP is an intentional architectural design: extractive QA proposes answers only when authoritative contract clauses or formal certificates exist, and routes unverified items to human review rather than hallucinating.

## 2. Breakdown by Extraction Method

| Extraction Method | Category Description | Question Count | Share (%) |
|---|---|---|---|
| `CONTRACT_CLAUSE` | Extractive QA (CUAD Model for MSAs, IP agreements, SLAs) | 39 | 18.7% |
| `FINANCIAL_TABLE` | Deterministic parsing (Formulas on P&L, burn, cap tables, concentration) | 32 | 15.3% |
| `CERTIFICATE_OR_REPORT` | Regex / Keyword detector (SOC 2, ISO, FDA 510(k), Good Standing) | 27 | 12.9% |
| `POLICY_DOC` | Pattern & presence detector (WISP, BCP/DR, incident response) | 27 | 12.9% |
| `SELF_ATTESTED` | Manual response required (governance questions, unmapped rules) | 84 | 40.2% |
| **Total** | | **209** | **100.0%** |

## 3. Breakdown by Industry

| Industry | Total | Auto-Extractable | Manual Required | Auto Coverage % |
|---|---|---|---|---|
| `ENERGY` | 17 | 2 | 15 | 11.8% |
| `FINTECH` | 23 | 5 | 18 | 21.7% |
| `HEALTHCARE` | 45 | 15 | 30 | 33.3% |
| `MANUFACTURING` | 18 | 4 | 14 | 22.2% |
| `SOFTWARE` | 18 | 11 | 7 | 61.1% |
| `UNIVERSAL` | 88 | 88 | 0 | 100.0% |

## 4. Breakdown by Dimension

| Dimension | Total | Contract QA | Financial Formula | Cert / Regex | Policy Detect | Manual |
|---|---|---|---|---|---|---|
| `CUSTOMER_MARKET` | 8 | 4 | 2 | 1 | 1 | 0 |
| `FIN_CONTROLS` | 17 | 4 | 3 | 5 | 1 | 4 |
| `FIN_PERFORMANCE` | 10 | 0 | 8 | 0 | 0 | 2 |
| `GOVERNANCE` | 8 | 3 | 1 | 1 | 3 | 0 |
| `HUMAN_CAPITAL` | 12 | 3 | 2 | 0 | 3 | 4 |
| `INDUSTRY_REG` | 14 | 0 | 0 | 5 | 0 | 9 |
| `LEGAL_IP_REG` | 53 | 9 | 0 | 5 | 1 | 38 |
| `MGMT_DEPTH` | 8 | 2 | 1 | 1 | 4 | 0 |
| `OPS_TECH_CYBER` | 52 | 3 | 1 | 9 | 12 | 27 |
| `PROFIT_CASHFLOW` | 8 | 1 | 7 | 0 | 0 | 0 |
| `REVENUE_QUALITY` | 9 | 2 | 6 | 0 | 1 | 0 |
| `TXN_READINESS` | 10 | 8 | 1 | 0 | 1 | 0 |

## 5. Contract Clause Routing & CUAD Taxonomy Validation

Each question below utilizes `CONTRACT_CLAUSE` extraction. Its design-time category is validated against the **41 official CUAD labels** established by The Atticus Project.

| Question ID | Question Text (Summary) | Mapped CUAD Category | CUAD Validation Status | Target Document Types |
|---|---|---|---|---|
| `ENERGY_06` | Are binding long-term Power Purchase Agreements (PPAs) or virtual PPAs (... | `Revenue/Profit Sharing` | VALID (Official CUAD Label) | `ppa_agreement` |
| `FIN_TECH_10` | For bank-sponsored models, are active BaaS (Banking-as-a-Service) agreem... | `Termination for Convenience` | VALID (Official CUAD Label) | `customer_contract, sla` |
| `SAAS_04` | Do active enterprise Service Level Agreements (SLAs) contain unlimited f... | `Cap on Liability` | VALID (Official CUAD Label) | `customer_contract, msa` |
| `SAAS_05` | Are proprietary machine learning models trained on user data, and do cus... | `IP Ownership Assignment` | VALID (Official CUAD Label) | `terms_of_service` |
| `SAAS_06` | Does the software architecture rely on any viral copyleft open-source li... | `License Grant` | VALID (Official CUAD Label) | `code_audit, ip_agreement` |
| `ENG_PHASE1_01` | Are there executed Power Purchase Agreements (PPAs) or off-take contract... | `Revenue/Profit Sharing` | VALID (Official CUAD Label) | `ppa_agreement` |
| `HLTH_CYBER_05` | Is there a documented postmarket vulnerability management plan outlining... | `Termination for Convenience` | VALID (Official CUAD Label) | `customer_contract, sla` |
| `SAAS_COPYLEFT_01` | Does the software architecture rely on any viral copyleft open-source li... | `License Grant` | VALID (Official CUAD Label) | `code_audit, ip_agreement` |
| `SAAS_SLA_01` | Do active enterprise Service Level Agreements (SLAs) contain unlimited f... | `Cap on Liability` | VALID (Official CUAD Label) | `customer_contract, msa` |
| `SAAS_AIDATA_01` | Are proprietary machine learning models trained on user/customer data, a... | `IP Ownership Assignment` | VALID (Official CUAD Label) | `terms_of_service` |
| `CORE_GOV_03` | Does the company own or control, directly or indirectly, any equity inte... | `Affiliate License-Licensor` | VALID (Official CUAD Label) | `corporate_structure, spa` |
| `CORE_GOV_05` | Are there any transactions, contracts, outstanding loans, or payment com... | `Affiliate License-Licensee` | VALID (Official CUAD Label) | `promissory_notes, related_party_agreements` |
| `CORE_GOV_06` | Does the Certificate of Incorporation contain clear class voting thresho... | `Change Of Control` | VALID (Official CUAD Label) | `restated_certificate_of_incorporation` |
| `CORE_FIN_08` | Are all credit agreements, bank debt facilities, letters of credit, and ... | `Termination For Convenience` | VALID (Official CUAD Label) | `credit_agreements, loan_documents` |
| `CORE_LEGAL_01` | Are there any pending, threatened, or ongoing claims, lawsuits, administ... | `Covenant Not To Sue` | VALID (Official CUAD Label) | `legal_audit, disclosure_schedule` |
| `CORE_IP_01` | Does the company own or possess valid, unencumbered rights to all patent... | `IP Ownership Assignment` | VALID (Official CUAD Label) | `patent_filings, trademark_filings, ip_agreements` |
| `CORE_IP_02` | Has every current and former founder, employee, and independent contract... | `IP Ownership Assignment` | VALID (Official CUAD Label) | `piia_agreement, contractor_agreement` |
| `CORE_IP_03` | Does the company's proprietary software code include or link with any op... | `License Grant` | VALID (Official CUAD Label) | `sca_scan_report, code_audit` |
| `CORE_LEGAL_02` | Are all material agreements (customer contracts > $100k, debt instrument... | `Termination For Convenience` | VALID (Official CUAD Label) | `material_contracts, msa` |
| `CORE_OPS_02` | Does the company own or lease all tangible personal property and equipme... | `Termination For Convenience` | VALID (Official CUAD Label) | `equipment_leases, asset_schedule` |
| `CORE_OPS_06` | Are all commercial office, lab, or warehouse lease agreements fully exec... | `Termination For Convenience` | VALID (Official CUAD Label) | `commercial_leases, estoppel_certificates` |
| `CORE_HR_03` | Are all C-level executives and key personnel bound by executed employmen... | `Post-Termination Services` | VALID (Official CUAD Label) | `executive_contracts, offer_letters` |
| `CORE_HR_07` | Do any executive or employee contracts trigger single-trigger or double-... | `Change Of Control` | VALID (Official CUAD Label) | `severance_agreements, equity_plans` |
| `CORE_HR_08` | Are proprietary restrictive covenants (non-compete, non-solicitation, an... | `Non-Compete` | VALID (Official CUAD Label) | `restrictive_covenant_agreements` |
| `CORE_TXN_01` | Are there any side letters or special agreements that grant any sharehol... | `Most Favored Nation` | VALID (Official CUAD Label) | `side_letters, investor_agreements` |
| `CORE_TXN_02` | Do any active debt facilities, leases, customer contracts, or commercial... | `Change Of Control` | VALID (Official CUAD Label) | `commercial_leases, loan_agreements` |
| `CORE_TXN_03` | Have all holders of contractual or statutory preemptive rights, rights o... | `Rofr/Rofo/Rofn` | VALID (Official CUAD Label) | `rofr_waivers, investor_consents` |
| `CORE_TXN_06` | Are there any broker, finder, investment banking, or financial advisory ... | `Revenue/Profit Sharing` | VALID (Official CUAD Label) | `engagement_letters, broker_agreements` |
| `CORE_TXN_07` | Do any existing shareholders possess demand, piggyback, or Form S-3 regi... | `Affiliate License-Licensee` | VALID (Official CUAD Label) | `investors_rights_agreement` |
| `CORE_TXN_08` | Does the company's charter, bylaws, or any contract contain shareholder ... | `Change Of Control` | VALID (Official CUAD Label) | `bylaws, charter` |
| `CORE_CASH_FLOW_08` | Does the company have any outstanding earnout liabilities, deferred acqu... | `Revenue/Profit Sharing` | VALID (Official CUAD Label) | `asset_purchase_agreements` |
| `CORE_REV_QUAL_04` | What percentage of enterprise customer contracts have a committed term o... | `Renewal Term` | VALID (Official CUAD Label) | `msa, order_forms` |
| `CORE_REV_QUAL_07` | Do standard multi-year customer agreements include annual price escalati... | `Price Restrictions` | VALID (Official CUAD Label) | `customer_agreements, msa` |
| `CORE_MGMT_03` | Are there contractual key-person clauses in credit facilities, major cus... | `Termination For Convenience` | VALID (Official CUAD Label) | `credit_agreements, investor_agreements` |
| `CORE_MGMT_08` | Does the company maintain a formal Advisory Board under signed advisory ... | `Post-Termination Services` | VALID (Official CUAD Label) | `advisor_agreements` |
| `CORE_CUST_01` | Has any top-20 customer terminated, failed to renew, or communicated wri... | `Termination For Convenience` | VALID (Official CUAD Label) | `customer_notices, churn_reports` |
| `CORE_CUST_02` | Do any active customer agreements contain Most Favored Nation (MFN) pric... | `Most Favored Nation` | VALID (Official CUAD Label) | `customer_contracts, msa` |
| `CORE_CUST_03` | Has the company granted any customer, distributor, or channel partner ex... | `Exclusivity` | VALID (Official CUAD Label) | `distribution_agreements, reseller_contracts` |
| `CORE_CUST_06` | Are there any unresolved customer disputes, formal service credit reques... | `Warranty Duration` | VALID (Official CUAD Label) | `customer_complaints, warranty_log` |

**CUAD Validation Summary:** 39 total contract clause questions evaluated. **39** match official CUAD labels, **0** flagged as unofficial.

---
*Report generated automatically by `apps/api/seeds/coverage_report.py`.*