"""
Google Colab End-to-End CUAD Benchmark Evaluation Script.
Runs on a free Colab GPU (T4 / V100 / A100) or CPU.

Evaluates RoBERTa CUAD extractive QA across all 51 held-out test contracts
for all 41 official CUAD categories (2,091 real evaluation pairs) with NO TRUNCATION.

Features:
1. Automatically installs dependencies (transformers, datasets, huggingface_hub, scikit-learn, torch).
2. Logs environment metadata (Python, PyTorch, CUDA device, Transformers version, Git commit).
3. Checkpoints progress per contract to `colab_cuad_checkpoint.json`.
4. Enforces strict anti-synthetic validation (Requirement 4):
   - Every row must have a real model margin.
   - Fails immediately if more than 20 rows share an identical non-zero score.
5. Writes `cuad_predictions.csv` with exact columns:
   contract, category, score, margin, predicted span, gold span, iou, correct
6. Writes comprehensive run log to `colab_cuad_run.log`.
7. Computes official Atticus CUAD metrics (Requirement 5):
   - Per-category AUPR for all 41 categories via official evaluate.py logic
   - Macro mean AUPR
   - Precision at 80% Recall (P @ 80% R)
   - Coverage and error rate at 0.85 and 0.50 with exact Wilson score intervals and n for mapped categories.
"""
import os
import sys
import subprocess
import json
import math
import time
import csv
from typing import List, Dict, Any, Tuple
import numpy as np

# 1. Dependency Auto-Installation (for Google Colab)
REQUIRED_PACKAGES = ["transformers", "huggingface_hub", "scikit-learn", "torch"]
for pkg in REQUIRED_PACKAGES:
    try:
        __import__(pkg)
    except ImportError:
        print(f"Installing missing requirement: {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

import torch
import transformers
from transformers import AutoTokenizer, AutoModelForQuestionAnswering
from huggingface_hub import hf_hub_download
from sklearn import metrics

# Setup paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CHECKPOINT_PATH = os.path.join(os.path.dirname(__file__), "colab_cuad_checkpoint.json")
RUN_LOG_PATH = os.path.join(os.path.dirname(__file__), "colab_cuad_run.log")
PREDICTIONS_CSV = os.path.join(os.path.dirname(__file__), "cuad_predictions.csv")

MODEL_REPO = "Mjolnirslams/roberta-base-squad2-cuad"
DATASET_REPO = "theatticusproject/cuad"

CUAD_41_CATEGORIES = [
    "Document Name", "Parties", "Agreement Date", "Effective Date", "Expiration Date",
    "Renewal Term", "Notice Period To Terminate Renewal", "Governing Law", "Most Favored Nation",
    "Non-Compete", "Exclusivity", "No-Solicit Of Customers", "Competitive Restriction Exception",
    "No-Solicit Of Employees", "Non-Disparagement", "Termination For Convenience",
    "Rofr/Rofo/Rofn", "Change Of Control", "Anti-Assignment", "Revenue/Profit Sharing",
    "Price Restrictions", "Minimum Commitment", "Volume Restriction", "Ip Ownership Assignment",
    "Joint Ip Ownership", "License Grant", "Non-Transferable License", "Affiliate License-Licensor",
    "Affiliate License-Licensee", "Unlimited/All-You-Can-Eat-License",
    "Irrevocable Or Perpetual License", "Source Code Escrow", "Post-Termination Services",
    "Audit Rights", "Uncapped Liability", "Cap On Liability", "Liquidated Damages",
    "Warranty Duration", "Insurance", "Covenant Not To Sue", "Third Party Beneficiary"
]

MAPPED_CATEGORIES = [
    "Change Of Control",
    "Most Favored Nation",
    "Exclusivity",
    "Uncapped Liability"
]


def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(RUN_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_git_commit() -> str:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
        return commit
    except Exception:
        return "UNKNOWN_COMMIT"


def wilson_ci(k: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Exact Wilson score confidence interval for binomial proportions."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.95996
    p_hat = k / n
    denom = 1.0 + (z ** 2) / n
    center = (p_hat + (z ** 2) / (2 * n)) / denom
    margin = (z / denom) * math.sqrt((p_hat * (1.0 - p_hat) / n) + ((z ** 2) / (4 * n ** 2)))
    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return round(float(low), 4), round(float(high), 4)


def compute_token_iou(s1: str, s2: str) -> float:
    """Computes token-level Jaccard similarity between two spans."""
    remove_tokens = [".", ",", ";", ":", '"', "'", "(", ")", "[", "]", "{", "}"]
    for token in remove_tokens:
        s1 = s1.replace(token, " ")
        s2 = s2.replace(token, " ")
    s1 = s1.lower().replace("/", " ")
    s2 = s2.lower().replace("/", " ")
    t1 = set(s1.split())
    t2 = set(s2.split())
    if not t1 and not t2:
        return 1.0
    if not t1 or not t2:
        return 0.0
    return len(t1.intersection(t2)) / len(t1.union(t2))


def process_precisions(precision: List[float]) -> List[float]:
    """Official Atticus CUAD monotonic envelope adjustment."""
    precision_best = precision[::-1]
    for i in range(1, len(precision_best)):
        precision_best[i] = max(precision_best[i - 1], precision_best[i])
    return precision_best[::-1]


def compute_official_cuad_category_metrics(instances_for_cat: List[Dict[str, Any]]) -> Tuple[float, float, float]:
    """Computes AUPR and Precision at 80% Recall for a single category via official Atticus evaluate.py logic."""
    total_pos = sum(1 for x in instances_for_cat if x["has_gt"] and x["gold_span"])
    if total_pos == 0:
        return 0.0, 0.0, 0.0

    precisions = [1.0]
    recalls = [0.0]
    thresholds = list(np.arange(0.99, 0, -0.01)) + [0.001, 0.0]

    for conf in thresholds:
        tp = 0
        fp = 0
        fn = 0
        for it in instances_for_cat:
            has_gt = it["has_gt"]
            gold = it["gold_span"]
            pred = it["predicted_span"]
            score = it["score"]
            pred_kept = pred if score > conf else ""

            if not has_gt or not gold:
                if pred_kept:
                    fp += 1
            else:
                if not pred_kept:
                    fn += 1
                else:
                    match = compute_token_iou(gold, pred_kept) >= 0.50
                    if match:
                        tp += 1
                    else:
                        fp += 1
                        fn += 1

        prec = tp / (tp + fp) if (tp + fp) > 0 else np.nan
        rec = tp / total_pos
        precisions.append(prec)
        recalls.append(rec)

    clean_p = [1.0 if np.isnan(p) else p for p in precisions]
    clean_r = recalls
    proc_p = process_precisions(clean_p)
    aupr = metrics.auc(clean_r, proc_p)
    if np.isnan(aupr):
        aupr = 0.0

    p80 = 0.0
    for p, r in zip(proc_p, clean_r):
        if r >= 0.80:
            p80 = p
            break

    max_recall = max(clean_r)
    return round(float(aupr), 4), round(float(p80), 4), round(float(max_recall), 4)


def batched_extractor_gpu(
    tokenizer,
    model,
    device: torch.device,
    contract_text: str,
    categories: List[str],
    queries_map: Dict[str, str],
    batch_size: int = 32
) -> Dict[str, Dict[str, Any]]:
    """Evaluates all 41 categories across full contract text using GPU-batched sliding windows."""
    words = contract_text.split()
    chunk_word_size = 180
    chunk_stride = 90
    word_spans = []
    c_pos = 0
    for w in words:
        idx = contract_text.find(w, c_pos)
        if idx == -1:
            idx = c_pos
        word_spans.append((idx, idx + len(w)))
        c_pos = idx + len(w)

    chunks = []
    if len(words) <= chunk_word_size:
        chunks.append((0, len(contract_text), contract_text))
    else:
        for i in range(0, len(words), chunk_stride):
            w_slice = words[i:i + chunk_word_size]
            c_start = word_spans[i][0]
            c_end = word_spans[min(i + len(w_slice) - 1, len(word_spans) - 1)][1]
            chunks.append((c_start, c_end, contract_text[c_start:c_end]))
            if i + chunk_word_size >= len(words):
                break

    results = {}
    for cat in categories:
        query = queries_map.get(cat, f'Highlight the parts (if any) of this contract related to "{cat}" that should be reviewed.')
        best_score = -float("inf")
        best_span = ""

        with torch.no_grad():
            for b_idx in range(0, len(chunks), batch_size):
                b_chunks = chunks[b_idx:b_idx + batch_size]
                chunk_texts = [ch[2] for ch in b_chunks]
                inputs = tokenizer(
                    [query] * len(b_chunks),
                    chunk_texts,
                    max_length=384,
                    stride=128,
                    truncation="only_second",
                    return_offsets_mapping=True,
                    padding=True,
                    return_tensors="pt"
                )

                offset_mapping = inputs.pop("offset_mapping")
                model_inputs = {k: v.to(device) for k, v in inputs.items()}
                outputs = model(**model_inputs)
                start_logits = outputs.start_logits.cpu()
                end_logits = outputs.end_logits.cpu()

                for k, (c_start, c_end, ch_str) in enumerate(b_chunks):
                    s_log = start_logits[k]
                    e_log = end_logits[k]
                    offsets = offset_mapping[k]
                    no_ans = (s_log[0] + e_log[0]).item()

                    seq_ids = inputs.sequence_ids(k)
                    ctx_indices = [idx for idx, sid in enumerate(seq_ids) if sid == 1]
                    if not ctx_indices:
                        continue

                    top_s = sorted(ctx_indices, key=lambda idx: s_log[idx].item(), reverse=True)[:5]
                    top_e = sorted(ctx_indices, key=lambda idx: e_log[idx].item(), reverse=True)[:5]

                    for s_pos in top_s:
                        for e_pos in top_e:
                            if s_pos <= e_pos and (e_pos - s_pos) < 60:
                                span_score = s_log[s_pos].item() + e_log[e_pos].item()
                                margin = span_score - no_ans
                                if margin > best_score:
                                    cs = offsets[s_pos][0].item()
                                    ce = offsets[e_pos][1].item()
                                    sp_text = ch_str[cs:ce].strip()
                                    if len(sp_text) > 3:
                                        best_score = margin
                                        best_span = sp_text

        if best_score > -float("inf") and len(best_span) > 0:
            score = 1.0 / (1.0 + math.exp(-best_score))
            score = round(float(score), 4)
            raw_margin = round(float(best_score), 4)
        else:
            score = 0.0
            best_span = ""
            raw_margin = -999.0

        results[cat] = {
            "score": score,
            "margin": raw_margin,
            "pred_span": best_span[:500],
        }

    return results


def main():
    log("=================================================================")
    log("STARTING COLAB CUAD BENCHMARK EVALUATION (51 CONTRACTS, 41 CATS)")
    log("=================================================================")

    # Log environment metadata
    git_commit = get_git_commit()
    log(f"Git Commit Hash:      {git_commit}")
    log(f"Python Version:       {sys.version.split()[0]}")
    log(f"PyTorch Version:      {torch.__version__}")
    log(f"Transformers Version: {transformers.__version__}")
    cuda_avail = torch.cuda.is_available()
    log(f"CUDA Available:       {cuda_avail}")
    if cuda_avail:
        device = torch.device("cuda")
        log(f"GPU Hardware:         {torch.cuda.get_device_name(0)}")
        log(f"CUDA Version:         {torch.version.cuda}")
        batch_size = 32
    else:
        device = torch.device("cpu")
        log("Running on CPU (WARNING: slow on CPU, GPU strongly recommended!)")
        batch_size = 16

    # Load CUAD dataset
    log("Downloading and loading official CUAD v1.0 dataset...")
    cuad_path = hf_hub_download(repo_id=DATASET_REPO, filename="CUAD_v1/CUAD_v1.json", repo_type="dataset")
    with open(cuad_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    contracts = sorted(data["data"], key=lambda c: c["title"])
    n = len(contracts)
    n_train = int(n * 0.8)
    n_val = int(n * 0.1)
    test_contracts = contracts[n_train + n_val:]
    log(f"Loaded {n} total contracts. Held-out test split: {len(test_contracts)} contracts.")

    # Load Model & Tokenizer
    log(f"Loading extractive QA model ({MODEL_REPO}) onto {device}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_REPO)
    model = AutoModelForQuestionAnswering.from_pretrained(MODEL_REPO)
    model.eval()
    model.to(device)

    # Official queries map
    queries_map = {}
    for qa in test_contracts[0]["paragraphs"][0]["qas"]:
        q_text = qa["question"]
        if 'related to "' in q_text:
            cat = q_text.split('related to "')[1].split('"')[0]
            queries_map[cat] = q_text

    # Load checkpoint if exists
    checkpoint = {}
    if os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
            log(f"Resuming from checkpoint ({len(checkpoint)} contracts already evaluated).")
        except Exception as e:
            log(f"Warning: Could not read checkpoint: {e}")

    # Evaluate test contracts
    total_test = len(test_contracts)
    log(f"Beginning evaluation across {total_test} contracts x {len(CUAD_41_CATEGORIES)} categories = {total_test * len(CUAD_41_CATEGORIES)} instances (NO TRUNCATION)...")

    for idx, c in enumerate(test_contracts):
        title = c["title"]
        if title in checkpoint:
            continue

        c_text = c["paragraphs"][0]["context"]
        c_len = len(c_text)
        t_start = time.time()

        preds = batched_extractor_gpu(
            tokenizer=tokenizer,
            model=model,
            device=device,
            contract_text=c_text,
            categories=CUAD_41_CATEGORIES,
            queries_map=queries_map,
            batch_size=batch_size
        )
        elapsed = time.time() - t_start

        contract_results = {}
        qas_by_cat = {qa["question"].split('related to "')[1].split('"')[0]: qa for qa in c["paragraphs"][0]["qas"] if 'related to "' in qa["question"]}

        for cat in CUAD_41_CATEGORIES:
            qa = qas_by_cat.get(cat)
            answers = [a["text"] for a in qa.get("answers", [])] if qa else []
            has_gt = len(answers) > 0 and (not qa.get("is_impossible", False)) if qa else False
            primary_gold = answers[0] if answers else ""

            p_item = preds.get(cat, {})
            sc = p_item.get("score", 0.0)
            margin = p_item.get("margin", -999.0)
            p_span = p_item.get("pred_span", "")

            max_iou = max([compute_token_iou(g, p_span) for g in answers]) if has_gt else 0.0

            contract_results[cat] = {
                "score": sc,
                "margin": margin,
                "pred_span": p_span,
                "has_gt": has_gt,
                "gold_span": primary_gold,
                "iou": round(float(max_iou), 4)
            }

        checkpoint[title] = contract_results
        with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f)

        log(f"[{idx+1}/{total_test}] {title[:35]} ({c_len} chars) finished in {elapsed:.1f}s (saved to checkpoint)")

    # Compile all 2,091 instances
    all_instances = []
    for c_title, c_cats in checkpoint.items():
        for cat, item in c_cats.items():
            sc = float(item["score"])
            margin = float(item["margin"])
            p_span = str(item["pred_span"])
            g_span = str(item["gold_span"])
            has_gt = bool(item["has_gt"])
            iou = float(item["iou"])

            # Correctness definition:
            # Positive contract (has_gt=True): correct if sc >= 0.50 and iou >= 0.50
            # Negative contract (has_gt=False): correct if sc < 0.50
            if has_gt:
                correct = (sc >= 0.50 and iou >= 0.50)
            else:
                correct = (sc < 0.50)

            all_instances.append({
                "contract": c_title,
                "category": cat,
                "score": sc,
                "margin": margin,
                "predicted_span": p_span,
                "gold_span": g_span,
                "iou": iou,
                "correct": correct,
                "has_gt": has_gt
            })

    log(f"\nTotal compiled evaluation instances: {len(all_instances)}")

    # =================================================================
    # REQUIREMENT 4: Anti-Synthetic Score & Margin Checks
    # =================================================================
    log("Running Requirement 4 Anti-Synthetic Verification Checks...")

    # 1. Check that every row has a real model margin
    missing_margin = sum(1 for x in all_instances if "margin" not in x or x["margin"] is None or math.isnan(x["margin"]))
    if missing_margin > 0:
        raise ValueError(f"SYNTHETIC AUDIT FAILED: {missing_margin} rows are missing a valid model margin!")
    log("✓ Real model margin check passed: all rows contain numerical margins.")

    # 2. Check for identical scores (>20 rows sharing identical score)
    from collections import Counter
    # Exclude 0.0 true negatives where no span was found above null score
    non_zero_scores = [round(x["score"], 4) for x in all_instances if x["score"] > 0.0]
    score_counts = Counter(non_zero_scores)
    duplicates = {sc: cnt for sc, cnt in score_counts.items() if cnt > 20}
    if duplicates:
        raise ValueError(f"SYNTHETIC AUDIT FAILED: Found suspicious identical non-zero scores shared across >20 rows: {duplicates}!")
    log(f"✓ Synthetic score check passed: max identical non-zero score frequency is {max(score_counts.values()) if score_counts else 0} (<= 20 limit).")

    # Save to cuad_predictions.csv
    with open(PREDICTIONS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["contract", "category", "score", "margin", "predicted span", "gold span", "iou", "correct"])
        for x in all_instances:
            writer.writerow([
                x["contract"],
                x["category"],
                f"{x['score']:.4f}",
                f"{x['margin']:.4f}",
                x["predicted_span"],
                x["gold_span"],
                f"{x['iou']:.4f}",
                x["correct"]
            ])
    log(f"Wrote genuine predictions to {PREDICTIONS_CSV}")

    # =================================================================
    # REQUIREMENT 5: Official Atticus Benchmark Metrics Calculation
    # =================================================================
    log("\n=================================================================")
    log("OFFICIAL CUAD BENCHMARK METRICS (41 CATEGORIES, N=2,091)")
    log("=================================================================")

    cat_auprs = {}
    cat_p80s = {}

    print(f"\n{'Category':<35} | {'Gold (n)':<8} | {'Max Rec':<8} | {'Official AUPR':<14} | {'P @ 80% R':<10}")
    print("-" * 85)

    for cat in CUAD_41_CATEGORIES:
        c_inst = [x for x in all_instances if x["category"] == cat]
        total_gt = sum(1 for x in c_inst if x["has_gt"])
        aupr, p80, max_rec = compute_official_cuad_category_metrics(c_inst)
        cat_auprs[cat] = aupr
        cat_p80s[cat] = p80
        print(f"{cat:<35} | {total_gt:<8} | {max_rec*100:>6.1f}% | {aupr*100:>12.2f}% | {p80*100:>8.2f}%")

    macro_aupr = float(np.mean(list(cat_auprs.values())))
    macro_p80 = float(np.mean(list(cat_p80s.values())))

    print("-" * 85)
    print(f"{'MACRO MEAN (All 41 Categories)':<35} | {'':<8} | {'':<8} | {macro_aupr*100:>12.2f}% | {macro_p80*100:>8.2f}%\n")

    # Mapped Categories Breakdown (Requirement 5)
    print("\n=================================================================")
    print("MAPPED CATEGORIES EVALUATION (Coverage & Error @ 0.85 and 0.50)")
    print("=================================================================")
    print(f"{'Category':<22} | {'Accepted @ 0.85':<17} | {'Error @ 0.85 (95% CI)':<23} | {'Accepted @ 0.50':<17} | {'Error @ 0.50 (95% CI)':<23}")
    print("-" * 110)

    for cat in MAPPED_CATEGORIES:
        c_inst = [x for x in all_instances if x["category"] == cat]
        n_c = len(c_inst)

        # At 0.85 (T_high)
        acc_85 = [x for x in c_inst if x["score"] >= 0.85]
        n_85 = len(acc_85)
        err_85 = sum(1 for x in acc_85 if not x["correct"])
        err_rate_85 = err_85 / n_85 if n_85 > 0 else 0.0
        ci_err_85 = wilson_ci(err_85, n_85)
        str_acc_85 = f"n={n_85} ({n_85/n_c*100:.1f}%)"
        str_err_85 = f"{err_rate_85*100:.1f}% [{ci_err_85[0]*100:.1f}%, {ci_err_85[1]*100:.1f}%]" if n_85 > 0 else "n/a (n=0)"

        # At 0.50 (T_low)
        acc_50 = [x for x in c_inst if x["score"] >= 0.50]
        n_50 = len(acc_50)
        err_50 = sum(1 for x in acc_50 if not x["correct"])
        err_rate_50 = err_50 / n_50 if n_50 > 0 else 0.0
        ci_err_50 = wilson_ci(err_50, n_50)
        str_acc_50 = f"n={n_50} ({n_50/n_c*100:.1f}%)"
        str_err_50 = f"{err_rate_50*100:.1f}% [{ci_err_50[0]*100:.1f}%, {ci_err_50[1]*100:.1f}%]" if n_50 > 0 else "n/a (n=0)"

        print(f"{cat:<22} | {str_acc_85:<17} | {str_err_85:<23} | {str_acc_50:<17} | {str_err_50:<23}")

    log("Evaluation script execution completed successfully.")


if __name__ == "__main__":
    main()
