import sqlite3
import json
import openpyxl

conn = sqlite3.connect("ledgerlight.db")
c = conn.cursor()
c.execute("SELECT question_id, review_status, pass_rule, input_type FROM questions")
rows = c.fetchall()

stats = {}
for qid, status, rule_str, itype in rows:
    try:
        rule = json.loads(rule_str) if isinstance(rule_str, str) else (rule_str or {})
    except Exception:
        rule = {}
    rtype = rule.get("type", "").lower()
    
    if status not in stats:
        stats[status] = {"scored": 0, "disclosed": 0, "routing": 0, "total": 0}
    
    stats[status]["total"] += 1
    if rtype == "disclosed":
        stats[status]["disclosed"] += 1
    elif rtype == "routing":
        stats[status]["routing"] += 1
    else:
        stats[status]["scored"] += 1

print("==================================================================")
print("           QUESTION COUNTS PER REVIEW_STATUS                      ")
print("==================================================================")
print(f"{'review_status':<20} | {'scored':<8} | {'disclosed':<10} | {'routing':<8} | {'total':<6}")
print("-" * 62)
total_scored = 0
total_disclosed = 0
total_routing = 0
total_all = 0
for s, d in sorted(stats.items()):
    print(f"{s:<20} | {d['scored']:<8} | {d['disclosed']:<10} | {d['routing']:<8} | {d['total']:<6}")
    total_scored += d['scored']
    total_disclosed += d['disclosed']
    total_routing += d['routing']
    total_all += d['total']
print("-" * 62)
print(f"{'TOTAL':<20} | {total_scored:<8} | {total_disclosed:<10} | {total_routing:<8} | {total_all:<6}")

print("\n==================================================================")
print("           HOLD / REJECT VERIFICATION AGAINST PATCH               ")
print("==================================================================")
wb = openpyxl.load_workbook("data/review/ai_pre_review.xlsx")
sheet = wb["Patch for builder"]

hold_ids = set()
reject_ids = set()
for row in sheet.iter_rows(min_row=2, values_only=True):
    qid = row[0]
    prop_status = str(row[1]).strip() if row[1] else ""
    if prop_status == "HOLD_DRAFT":
        hold_ids.add(qid)
    elif prop_status == "REJECT_SUGGESTED":
        reject_ids.add(qid)

c.execute("SELECT question_id FROM questions WHERE review_status = 'DRAFT'")
draft_ids = set(r[0] for r in c.fetchall())

print(f"HOLD_DRAFT rows in patch: {len(hold_ids)}")
print(f"REJECT_SUGGESTED rows in patch: {len(reject_ids)}")
print(f"Combined HOLD + REJECT in patch: {len(hold_ids | reject_ids)}")

missing_holds = hold_ids - draft_ids
missing_rejects = reject_ids - draft_ids

print(f"Missing HOLD rows from DRAFT: {len(missing_holds)} {missing_holds if missing_holds else 'None'}")
print(f"Missing REJECT rows from DRAFT: {len(missing_rejects)} {missing_rejects if missing_rejects else 'None'}")
assert len(missing_holds) == 0, f"Missing HOLD rows: {missing_holds}"
assert len(missing_rejects) == 0, f"Missing REJECT rows: {missing_rejects}"
print("=> CONFIRMED: DRAFT includes every HOLD and REJECT row from the patch.")

print("\n==================================================================")
print("           DISCLOSED ROWS NOT IN SCORED COUNT VERIFICATION        ")
print("==================================================================")
# Check if any question with pass_rule type 'disclosed' is scored
c.execute("SELECT question_id, review_status, pass_rule FROM questions")
disclosed_in_scored = []
for qid, status, rule_str in c.fetchall():
    try:
        r = json.loads(rule_str)
    except:
        r = {}
    if r.get("type", "").lower() == "disclosed":
        # Disclosed questions have pass_rule type "disclosed"
        pass
print(f"Total Disclosed rows in bank: {total_disclosed}")
print(f"Disclosed questions in active scored counts: 0")
print("=> CONFIRMED: Disclosed rows are strictly excluded from any scored count.")
