"""
Generates all 7 messy real-world test fixtures in tests/fixtures/messy_data_room/
Exercises:
1. messy_financials_thousands_quarterly.xlsx: Units in thousands ($ in '000s), quarterly columns, non-standard labels
2. messy_customer_concentration.csv: Non-standard headers, ACV, preambles, spaces
3. messy_bank_statement.pdf: Bank statement with accounting parentheses $(800,000.00), closing balance $2,250,000.00
4. scanned_page_soc2.pdf: Pure raster bitmap image without vector text layer to test OCR unavailability
5. messy_pnl_millions.xlsx: P&L in millions ($ in Millions) with Q1-Q4 columns and FY2025
6. messy_two_accounts_bank_statement.pdf: Bank PDF with two distinct bank accounts (Operating vs Payroll)
7. messy_split_customer.csv: Customer schedule with a customer split across two subsidiary entities
"""
import os
import csv
import openpyxl
import pymupdf
from PIL import Image, ImageDraw

out_dir = "tests/fixtures/messy_data_room"
os.makedirs(out_dir, exist_ok=True)

# 1. Messy Financial Statements XLSX ($ in Thousands, quarterly columns, irregular labels)
wb1 = openpyxl.Workbook()
ws1 = wb1.active
ws1.title = "Operations Summary"
ws1.append(["[CONFIDENTIAL - SYNTHETIC DATA]"])
ws1.append(["STATEMENT OF OPERATIONS (Figures in $ Thousands, USD)"])
ws1.append([])
ws1.append(["Line Item", "Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025", "FY2025 Total"])
ws1.append(["Total Net Revenue / Turnover", 2400, 2600, 2700, 2800, 10500])
ws1.append(["Cost of Sales and Contract Fulfillment", 480, 520, 540, 560, 2100])
ws1.append(["Gross Margin %", 80.0, 80.0, 80.0, 80.0, 80.0])
ws1.append(["Sales, Marketing & Acquisition", 700, 750, 800, 850, 3100])
ws1.append(["Engineering & Product Development", 550, 600, 620, 630, 2400])
ws1.append(["General, Administrative & Legal", 250, 270, 280, 300, 1100])
ws1.append(["Reported Operating EBITDA", 420, 440, 460, 480, 1800])
ws1.append(["Normalized EBITDA Adjustments", 30, 35, 40, 39, 144])
ws1.append(["Ending Cash & Equivalents", 1900, 2050, 2150, 2250, 2250])
ws1.append(["Average Monthly Cash Consumption", 130, 140, 145, 150, 150])
wb1.save(os.path.join(out_dir, "messy_financials_thousands_quarterly.xlsx"))

# 2. Messy Customer Concentration CSV (different labels, spacing, preambles)
with open(os.path.join(out_dir, "messy_customer_concentration.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["# INTERNAL DILIGENCE NOTE: Subject to final audit confirmation"])
    writer.writerow(["# Top Customer Billings for Fiscal Year 2025"])
    writer.writerow([])
    writer.writerow(["Client / Counterparty Name", "Annualized Contract Value (ACV)", "Share of Overall ARR"])
    writer.writerow(["Acme Global Enterprises Inc.", "$ 1,800,000.00 ", "17.1%"])
    writer.writerow(["Beta Corp Solutions", "$ 1,200,000.00 ", "11.4%"])
    writer.writerow(["Gamma Dynamics Holdings", "$ 900,000.00 ", "8.6%"])
    writer.writerow(["Delta Systems International", "$ 850,000.00 ", "8.1%"])
    writer.writerow(["Epsilon Research Labs", "$ 750,000.00 ", "7.1%"])
    writer.writerow(["Consolidated Other Active Accounts", "$ 5,000,000.00 ", "47.7%"])
    writer.writerow(["Total Consolidated ARR", "$ 10,500,000.00 ", "100.0%"])

# 3. PDF Bank Statement (Vector text with accounting negative parentheses and closing balance)
doc_bank = pymupdf.open()
page_bank = doc_bank.new_page(width=612, height=792)
bank_text = """FIRST NATIONAL HORIZON COMMERCIAL BANK
Commercial Banking Operations | Deposit Verification Services
100 Financial Plaza, Suite 400, New York, NY 10005

STATEMENT OF ACCOUNT
Account Holder: Acme Technology Holdings
Account Number: 8839-4410-09
Currency: USD ($)
Period: December 1, 2025 - December 31, 2025

ACCOUNT SUMMARY:
Opening Ledger Balance:                    $ 2,400,000.00
Total Merchant & Wire Credits:             $   650,000.00
Total Operating Debits:                    $(  800,000.00)
Closing Ledger Balance as of 12/31/2025:   $ 2,250,000.00
Certified Closing Balance:                 $ 2,250,000.00

OPERATIONAL METRICS:
Net Monthly Cash Outflow / Burn:           $   150,000.00
Average Monthly Burn Rate (L6M):           $   150,000.00

CERTIFICATION:
We hereby attest that the closing cash balance of $2,250,000.00 is true, accurate,
and fully reconciled against the institution's general ledger.
"""
page_bank.insert_text(pymupdf.Point(50, 70), bank_text, fontsize=10)
doc_bank.save(os.path.join(out_dir, "messy_bank_statement.pdf"))
doc_bank.close()

# 4. Scanned-page PDF to exercise OCR (Pure raster bitmap, 0 vector text characters)
img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
d = ImageDraw.Draw(img)
d.text((50, 60), "AICPA SOC 2 TYPE II INDEPENDENT AUDIT REPORT", fill=(30, 30, 30))
d.text((50, 90), "Service Organization: Acme Technology Holdings", fill=(40, 40, 40))
d.text((50, 120), "Audit Period: January 1, 2024 to December 31, 2024", fill=(40, 40, 40))
d.text((50, 150), "Auditor: Grant & Sterling LLP, Certified Public Accountants", fill=(40, 40, 40))
d.text((50, 190), "SCOPE AND OPINION:", fill=(30, 30, 30))
d.text((50, 220), "We have examined the description of controls relevant to Security and Availability.", fill=(50, 50, 50))
d.text((50, 250), "In our opinion, the controls were suitably designed and operated effectively.", fill=(50, 50, 50))
d.text((50, 290), "Trust Services Criteria: SOC 2 Type II Security, Availability, Confidentiality.", fill=(50, 50, 50))
img.save(os.path.join(out_dir, "scanned_page_soc2.pdf"), "PDF")

# 5. NEW FIXTURE 1: messy_pnl_millions.xlsx (Quarterly P&L in millions)
wb_mil = openpyxl.Workbook()
ws_mil = wb_mil.active
ws_mil.title = "P&L Summary"
ws_mil.append(["[CONFIDENTIAL BOARD PACK]"])
ws_mil.append(["Enterprise SaaS Holdings Inc. - Condensed Consolidated P&L"])
ws_mil.append(["(Currency in USD Millions, except share counts)"])
ws_mil.append([])
ws_mil.append(["Financial Metric", "Q1", "Q2", "Q3", "Q4", "FY2025"])
ws_mil.append(["Gross Revenue", 2.40, 2.60, 2.70, 2.80, 10.50])
ws_mil.append(["Cost of Goods Sold", 0.48, 0.52, 0.54, 0.56, 2.10])
ws_mil.append(["Gross Profit", 1.92, 2.08, 2.16, 2.24, 8.40])
ws_mil.append(["Gross Margin %", 80.0, 80.0, 80.0, 80.0, 80.0])
ws_mil.append(["Operating Expenses", 1.25, 1.35, 1.40, 1.45, 5.45])
ws_mil.append(["Reported EBITDA", 0.40, 0.45, 0.47, 0.48, 1.80])
ws_mil.append(["Management Add-backs", 0.03, 0.035, 0.04, 0.039, 0.144])
ws_mil.append(["Ending Cash Balance", 1.90, 2.05, 2.15, 2.25, 2.25])
ws_mil.append(["Net Monthly Burn", 0.13, 0.14, 0.145, 0.15, 0.15])
wb_mil.save(os.path.join(out_dir, "messy_pnl_millions.xlsx"))

# 6. NEW FIXTURE 2: messy_two_accounts_bank_statement.pdf (PDF statement with two accounts)
doc_two = pymupdf.open()
page_two = doc_two.new_page(width=612, height=792)
two_acc_text = """METROPOLITAN PACIFIC COMMERCIAL BANK
Treasury Management & Multi-Account Deposit Verification
500 Financial Way, San Francisco, CA 94104

CONSOLIDATED CLIENT ACCOUNT REPORT
Company: Acme Technology Holdings
Reporting Date: December 31, 2025

ACCOUNT 1: COMMERCIAL OPERATING CHECKING (#****-1001)
Opening Balance:                           $ 1,900,000.00
Monthly Disbursements / Debits:            $(  650,000.00)
Monthly Deposits / Collections:            $   500,000.00
Closing Ledger Balance:                    $ 1,750,000.00
Certified Available Funds:                 $ 1,750,000.00

ACCOUNT 2: PAYROLL & TAX ESCROW RESERVE (#****-2002)
Opening Balance:                           $   500,000.00
Transfers In from Operating:               $   150,000.00
Tax / Payroll Disbursements:               $(  150,000.00)
Closing Ledger Balance:                    $   500,000.00
Certified Available Funds:                 $   500,000.00

COMBINED TOTAL CASH AND EQUIVALENTS:       $ 2,250,000.00
CONSOLIDATED NET MONTHLY BURN RATE:        $   150,000.00

Bank Verification Officer:
Signature on File - Verified Consolidated Balance: $2,250,000.00
"""
page_two.insert_text(pymupdf.Point(50, 70), two_acc_text, fontsize=10)
doc_two.save(os.path.join(out_dir, "messy_two_accounts_bank_statement.pdf"))
doc_two.close()

# 7. NEW FIXTURE 3: messy_split_customer.csv (Top customer split across two subsidiary entities)
with open(os.path.join(out_dir, "messy_split_customer.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["# CUSTOMER CONTRACT AND BILLING SCHEDULE - BY AFFILIATE"])
    writer.writerow(["Entity / Billing Account", "Contracted ARR (USD)", "Notes"])
    writer.writerow(["Acme Global Enterprises - North America Division", "1000000.00", "Direct MSA"])
    writer.writerow(["Acme Global Enterprises - EMEA Subsidiary", "800000.00", "Affiliate Addendum"])
    writer.writerow(["Beta Corporation", "1200000.00", "Independent Account"])
    writer.writerow(["Gamma Dynamics Inc.", "900000.00", "Independent Account"])
    writer.writerow(["Delta Systems", "850000.00", "Independent Account"])
    writer.writerow(["All Remaining Customers Consolidated", "5750000.00", "Various"])
    writer.writerow(["Total Revenue", "10500000.00", "Reconciled Total ARR"])

print("All 7 messy fixtures generated successfully in", out_dir)
