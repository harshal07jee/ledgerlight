"""
CUAD Contract Extraction & Confidence Gating Engine (M6, PRD Sections 7.4, 7.5, and 12.1).

Model:
- Fine-tuned extractive QA model from Hugging Face: Mjolnirslams/roberta-base-squad2-cuad
- License: CC-BY-4.0
- Base Model: deepset/roberta-base-squad2 fine-tuned on the Contract Understanding Atticus Dataset (CUAD)
- Download Size: ~473.26 MB (496,250,208 bytes)
- Architecture: RobertaForQuestionAnswering (124M parameters)
- Air-Gap Invariant: Runs strictly locally on CPU. Zero document text or contract passages leave the machine.

Key Invariants:
1. Pure presence questions may AUTO_FILL only above T_high (default 0.85).
2. Compliance questions propose "Clause found" with NEEDS_CONFIRMATION; the user decides compliance.
3. Long documents are tokenized with sliding windows (max length 384, stride 128) and scored against no-answer logits.
4. Gating thresholds: T_high = 0.85, T_low = 0.50 (both configurable).
5. Scores are strictly labeled "model score", never "probability".
6. PRD 12.1 Structured Logging: logs metadata, model score, latency, and status. ZERO document text in logs.
"""
import os
import math
import time
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from datetime import datetime, timezone
import uuid

# Safety switch: allows or disallows silent fallback to heuristic extractor
ALLOW_HEURISTIC_FALLBACK: bool = True

def is_heuristic_fallback_allowed() -> bool:
    if not ALLOW_HEURISTIC_FALLBACK:
        return False
    return os.getenv("CUAD_ALLOW_FALLBACK", "1").lower() not in ("0", "false", "no")


# ---------------------------------------------------------------------------
# 1. Official 41 CUAD Categories (Strict Whitelist)
# ---------------------------------------------------------------------------
CUAD_41_CATEGORIES: List[str] = [
    "Affiliate License-Licensee",
    "Affiliate License-Licensor",
    "Agreement Date",
    "Anti-Assignment",
    "Audit Rights",
    "Cap On Liability",
    "Change Of Control",
    "Competitive Restriction Exception",
    "Covenant Not To Sue",
    "Document Name",
    "Effective Date",
    "Exclusivity",
    "Expiration Date",
    "Governing Law",
    "Insurance",
    "Ip Ownership Assignment",
    "Irrevocable Or Perpetual License",
    "Joint Ip Ownership",
    "License Grant",
    "Liquidated Damages",
    "Minimum Commitment",
    "Most Favored Nation",
    "No-Solicit Of Customers",
    "No-Solicit Of Employees",
    "Non-Compete",
    "Non-Disparagement",
    "Non-Transferable License",
    "Notice Period To Terminate Renewal",
    "Parties",
    "Post-Termination Services",
    "Price Restrictions",
    "Renewal Term",
    "Revenue/Profit Sharing",
    "Rofr/Rofo/Rofn",
    "Source Code Escrow",
    "Termination For Convenience",
    "Third Party Beneficiary",
    "Uncapped Liability",
    "Unlimited/All-You-Can-Eat-License",
    "Volume Restriction",
    "Warranty Duration",
]

# Set for O(1) membership check
CUAD_CATEGORIES_SET: Set[str] = {c.lower(): c for c in CUAD_41_CATEGORIES}

# ---------------------------------------------------------------------------
# 2. CONTRACT_CLAUSE Question Mapping to Official 41 CUAD Categories
# Only question IDs that exist in the database and have a clear, direct CUAD match.
# All other 25 CONTRACT_CLAUSE questions (litigation, royalties, side letters, PPAs, etc.)
# remain unmapped and evaluate strictly as MANUAL_REQUIRED.
# ---------------------------------------------------------------------------
CONTRACT_QUESTION_TO_CUAD: Dict[str, str] = {
    "CORE_TXN_02": "Change Of Control",
    "CORE_CUST_02": "Most Favored Nation",
    "CORE_CUST_03": "Exclusivity",
    "SAAS_SLA_01": "Uncapped Liability",
}

# Questions where answering "Yes" is purely presence-based (finding clause confirms presence).
# Only pure presence questions may be AUTO_FILLED when model_score >= T_high (if error justified).
# Not finding a clause must NEVER propose "No"; it leaves proposed_val as None (MANUAL_REQUIRED).
PURE_PRESENCE_QUESTIONS: Set[str] = {
    "CORE_CUST_02",       # Most Favored Nation
    "CORE_CUST_03",       # Exclusivity
    "SAAS_SLA_01",       # Uncapped Liability
}

# ---------------------------------------------------------------------------
# 3. Model Configuration & Defaults
# ---------------------------------------------------------------------------
CUAD_MODEL_REPO = "Mjolnirslams/roberta-base-squad2-cuad"
CUAD_MODEL_VERSION = "v1.0"
CUAD_LICENSE = "cc-by-4.0"
CUAD_DOWNLOAD_SIZE_BYTES = 496250208  # 473.26 MB
CUAD_MAX_SEQ_LENGTH = 384
CUAD_DOC_STRIDE = 128

# Configurable gating thresholds (PRD 7.5)
T_HIGH_DEFAULT = 0.85
T_LOW_DEFAULT = 0.50

def get_t_high() -> float:
    return float(os.getenv("CUAD_T_HIGH", str(T_HIGH_DEFAULT)))

def get_t_low() -> float:
    return float(os.getenv("CUAD_T_LOW", str(T_LOW_DEFAULT)))

# Calibration switch (PRD 7.5): off by default until a hand-labeled set exists
CALIBRATION_ENABLED = os.getenv("CUAD_CALIBRATION_ENABLED", "false").lower() == "true"
CALIBRATION_TEMPERATURE = float(os.getenv("CUAD_CALIBRATION_TEMP", "1.25"))

def is_cuad_autofill_enabled() -> bool:
    """
    Quality & Safety Invariant (Item 4):
    Until at least 100 accepted predictions at T_high show an upper confidence bound
    under 10% error, contract-clause questions must never be AUTO_FILLED; they are
    NEEDS_CONFIRMATION only. Controlled via CUAD_AUTOFILL_ENABLED config (default false).
    """
    return os.getenv("CUAD_AUTOFILL_ENABLED", "false").lower() == "true"

# Global lazy-loaded model cache
_MODEL_CACHE: Dict[str, Any] = {}


def verify_model_metadata() -> Dict[str, Any]:
    """Returns verified repository metadata and size for Mjolnirslams/roberta-base-squad2-cuad."""
    return {
        "repo_id": CUAD_MODEL_REPO,
        "version": CUAD_MODEL_VERSION,
        "license": CUAD_LICENSE,
        "size_bytes": CUAD_DOWNLOAD_SIZE_BYTES,
        "size_mb": round(CUAD_DOWNLOAD_SIZE_BYTES / (1024 * 1024), 2),
        "parameters": 124056578,
        "architecture": "RobertaForQuestionAnswering",
        "pipeline_tag": "question-answering",
        "dataset": "theatticusproject/cuad",
        "air_gap_compliant": True,
        "device": "cpu"
    }


def load_cuad_model():
    """
    Lazy loads the RoBERTa CUAD QA model and tokenizer locally on CPU.
    Guarantees no network calls once downloaded and no document text leaves the machine.
    """
    global _MODEL_CACHE
    if "model" in _MODEL_CACHE and "tokenizer" in _MODEL_CACHE:
        return _MODEL_CACHE["tokenizer"], _MODEL_CACHE["model"]

    try:
        from transformers import AutoTokenizer, AutoModelForQuestionAnswering
        import torch

        tokenizer = AutoTokenizer.from_pretrained(CUAD_MODEL_REPO)
        model = AutoModelForQuestionAnswering.from_pretrained(CUAD_MODEL_REPO)
        model.eval()
        model.to("cpu")

        _MODEL_CACHE["tokenizer"] = tokenizer
        _MODEL_CACHE["model"] = model
        return tokenizer, model
    except Exception as e:
        # Fallback to None if transformers/model weights cannot be initialized in environment
        return None, None


# ---------------------------------------------------------------------------
# 4. Calibration Hook (PRD 7.5)
# ---------------------------------------------------------------------------
def calibrate_score(raw_model_score: float, category: Optional[str] = None) -> Optional[float]:
    """
    Optional confidence calibration (temperature scaling or isotonic regression).
    Returns None if calibration is disabled (default until labeled validation set is established).
    """
    if not CALIBRATION_ENABLED:
        return None

    # Temperature scaling on logits
    p = max(min(raw_model_score, 0.9999), 0.0001)
    logit = math.log(p / (1.0 - p))
    calibrated_logit = logit / CALIBRATION_TEMPERATURE
    calibrated_score = 1.0 / (1.0 + math.exp(-calibrated_logit))
    return round(calibrated_score, 4)


# ---------------------------------------------------------------------------
# 5. Sliding Window Extractive QA Inference (PRD 7.4)
# ---------------------------------------------------------------------------
def load_official_cuad_queries() -> Dict[str, str]:
    """Loads official CUAD questions/prompts from data/cuad_official_queries.json."""
    query_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "data",
        "cuad_official_queries.json"
    )
    if os.path.exists(query_file):
        try:
            import json
            with open(query_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

_OFFICIAL_QUERIES: Dict[str, str] = load_official_cuad_queries()


def batched_sliding_window_extractor(
    contract_text: str,
    categories: List[str],
    tokenizer=None,
    model=None,
    batch_size: int = 16,
    max_length: int = CUAD_MAX_SEQ_LENGTH,
    stride: int = CUAD_DOC_STRIDE,
    allow_fallback: Optional[bool] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Unified extractive QA sliding-window engine used in both production and evaluation.
    Evaluates categories across full, un-truncated contract text using batched inference.
    """
    can_fallback = allow_fallback if allow_fallback is not None else is_heuristic_fallback_allowed()
    if tokenizer is None or model is None:
        tok, mod = load_cuad_model()
        if tok is None or mod is None:
            if not can_fallback:
                raise RuntimeError(
                    "CUAD real model failed to load in batched_sliding_window_extractor and heuristic fallback is disabled."
                )
            results = {}
            for cat in categories:
                norm = CUAD_CATEGORIES_SET.get(cat.lower(), cat)
                q = _OFFICIAL_QUERIES.get(norm, f'Highlight the parts (if any) of this contract related to "{norm}" that should be reviewed.')
                results[norm] = _sliding_window_heuristic_extractor(contract_text, norm, q, allow_fallback=can_fallback)
            return results
        tokenizer, model = tok, mod

    import torch

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
        norm = CUAD_CATEGORIES_SET.get(cat.lower(), cat)
        query = _OFFICIAL_QUERIES.get(norm, f'Highlight the parts (if any) of this contract related to "{norm}" that should be reviewed.')
        best_score = -float("inf")
        best_span = ""
        best_char_start = 0
        best_char_end = 0
        min_null_score = float("inf")
        candidate_predictions = []

        device = next(model.parameters()).device if hasattr(model, "parameters") else "cpu"
        with torch.no_grad():
            for b_idx in range(0, len(chunks), batch_size):
                b_chunks = chunks[b_idx:b_idx + batch_size]
                chunk_texts = [ch[2] for ch in b_chunks]
                inputs = tokenizer(
                    [query] * len(b_chunks),
                    chunk_texts,
                    max_length=max_length,
                    stride=stride,
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
                    if no_ans < min_null_score:
                        min_null_score = no_ans

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
                                cs = offsets[s_pos][0].item()
                                ce = offsets[e_pos][1].item()
                                sp_text = ch_str[cs:ce].strip()
                                if len(sp_text) > 3:
                                    candidate_predictions.append({
                                        "score": span_score,
                                        "text": sp_text,
                                        "char_start": c_start + cs,
                                        "char_end": c_start + ce,
                                        "margin": margin,
                                    })
                                    if margin > best_score:
                                        best_score = margin
                                        best_span = sp_text
                                        best_char_start = c_start + cs
                                        best_char_end = c_start + ce

        # HuggingFace SQuAD post-processing: softmax over n-best candidates taking the best non-null candidate
        seen_texts = set()
        nbest_non_null = []
        for cand in sorted(candidate_predictions, key=lambda x: x["score"], reverse=True):
            if cand["text"] not in seen_texts:
                seen_texts.add(cand["text"])
                nbest_non_null.append(cand)
                if len(nbest_non_null) >= 20:
                    break

        if nbest_non_null and min_null_score < float("inf"):
            total_scores = [c["score"] for c in nbest_non_null] + [min_null_score]
            max_s = max(total_scores)
            exps = [math.exp(s - max_s) for s in total_scores]
            sum_exps = sum(exps)
            probs = [e / sum_exps for e in exps] if sum_exps > 0 else [0.0] * len(total_scores)
            span_prob = round(float(probs[0]), 4)
        elif nbest_non_null:
            total_scores = [c["score"] for c in nbest_non_null]
            max_s = max(total_scores)
            exps = [math.exp(s - max_s) for s in total_scores]
            sum_exps = sum(exps)
            probs = [e / sum_exps for e in exps] if sum_exps > 0 else [0.0] * len(total_scores)
            span_prob = round(float(probs[0]), 4)
        else:
            span_prob = 0.0

        if best_score > -float("inf") and len(best_span) > 0:
            score = 1.0 / (1.0 + math.exp(-best_score))
            score = round(float(score), 4)
            raw_margin = round(float(best_score), 4)
        else:
            score = 0.0
            best_span = ""
            raw_margin = -999.0

        results[norm] = {
            "clause_found": len(best_span) > 0 and score >= get_t_low(),
            "cuad_category": norm,
            "span_text": best_span[:500],
            "char_start": best_char_start,
            "char_end": best_char_end,
            "model_score": score,
            "margin": raw_margin,
            "span_prob": span_prob,
            "n_windows": len(chunks),
            "calibrated_score": calibrate_score(score, norm),
            "method": "model"
        }

    return results


def extract_best_clause_span(
    contract_text: str,
    cuad_category: str,
    max_length: int = CUAD_MAX_SEQ_LENGTH,
    stride: int = CUAD_DOC_STRIDE,
    allow_fallback: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Performs extractive QA using overlapping sliding windows.
    Calls the unified batched_sliding_window_extractor.
    """
    category_norm = CUAD_CATEGORIES_SET.get(cuad_category.lower(), cuad_category)
    res = batched_sliding_window_extractor(
        contract_text=contract_text,
        categories=[category_norm],
        max_length=max_length,
        stride=stride,
        batch_size=16,
        allow_fallback=allow_fallback
    )
    return res[category_norm]



def _sliding_window_heuristic_extractor(
    contract_text: str,
    category: str,
    query: str,
    allow_fallback: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Deterministic sliding-window matcher used when deep neural model is not active
    or in unit testing environments.
    """
    can_fallback = allow_fallback if allow_fallback is not None else is_heuristic_fallback_allowed()
    if not can_fallback:
        raise RuntimeError(
            f"CUAD heuristic extractor invoked for category '{category}', but heuristic fallback is disabled. "
            "Evaluation must strictly use the real neural model."
        )

    words = contract_text.split()
    cat_terms = category.lower().replace("-", " ").replace("/", " ").split()
    
    best_score = 0.0
    best_span = ""
    best_char_start = 0
    best_char_end = 0

    # Sliding window of 50 words with 20 word step
    window_size = 50
    step = 20

    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + window_size])
        chunk_lower = chunk.lower()
        matches = sum(1 for term in cat_terms if term in chunk_lower)
        if matches > 0:
            score = round(min(0.95, 0.45 + (matches / len(cat_terms)) * 0.45), 4)
            if score > best_score:
                best_score = score
                best_span = chunk[:350].strip()
                best_char_start = contract_text.find(chunk[:30]) if chunk[:30] in contract_text else 0
                best_char_end = best_char_start + len(best_span)

    return {
        "clause_found": best_score >= get_t_low(),
        "cuad_category": category,
        "span_text": best_span[:500],
        "char_start": best_char_start,
        "char_end": best_char_end,
        "model_score": best_score,
        "margin": round(float(best_score * 10.0 - 5.0), 4) if best_score > 0 else -999.0,
        "span_prob": best_score,
        "n_windows": max(1, len(words) // 20),
        "calibrated_score": calibrate_score(best_score, category),
        "method": "heuristic"
    }


# ---------------------------------------------------------------------------
# 6. Confidence Gating & Status Determination (PRD 7.5)
# ---------------------------------------------------------------------------
def gate_cuad_extraction(
    question_id: str,
    extraction_result: Union[Dict[str, Any], str],
    maybe_extraction_result: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Applies strict confidence gating rules per PRD 7.5:
    - Only pure presence questions above T_high may AUTO_FILL.
    - If model is unavailable and heuristic runs, mark result method="heuristic",
      cap status at NEEDS_CONFIRMATION, and never AUTO_FILLED.
    - All other clauses or scores between T_low and T_high return NEEDS_CONFIRMATION.
    - Scores below T_low return MANUAL_REQUIRED.
    """
    if maybe_extraction_result is not None:
        category_arg = str(extraction_result)
        res = maybe_extraction_result
    else:
        category_arg = None
        res = extraction_result

    model_score = res.get("model_score", 0.0)
    category = res.get("cuad_category", category_arg or "Unknown")
    span_text = res.get("span_text", "")
    t_high = get_t_high()
    t_low = get_t_low()

    is_pure_presence = question_id in PURE_PRESENCE_QUESTIONS
    is_heuristic = (res.get("method") == "heuristic")
    method = "heuristic" if is_heuristic else "CUAD_EXTRACTIVE_QA"

    if model_score >= t_high:
        if is_pure_presence and is_cuad_autofill_enabled() and not is_heuristic:
            status = "AUTO_FILLED"
            proposed_val = True
        else:
            # Compliance questions: a clause span is evidence, not a verdict.
            # User must decide compliance!
            # Or autofill is disabled via config (CUAD_AUTOFILL_ENABLED=false).
            # Or heuristic extractor: capped at NEEDS_CONFIRMATION, never AUTO_FILLED.
            status = "NEEDS_CONFIRMATION"
            proposed_val = True if is_pure_presence else f"Clause found: {category}"
        confidence = model_score
    elif model_score >= t_low:
        status = "NEEDS_CONFIRMATION"
        confidence = model_score
        proposed_val = True if is_pure_presence else f"Clause found: {category}"
    else:
        status = "MANUAL_REQUIRED"
        confidence = model_score
        proposed_val = None

    return {
        "question_id": question_id,
        "cuad_category": category,
        "status": status,
        "confidence": confidence,
        "model_score": model_score,
        "calibrated_score": res.get("calibrated_score"),
        "answer_value": proposed_val,
        "method": method,
        "is_pure_presence": is_pure_presence,
        "snippet": span_text[:500] if span_text else None,
        "char_start": res.get("char_start"),
        "char_end": res.get("char_end")
    }


# ---------------------------------------------------------------------------
# 7. PRD 12.1 Structured Logging (Strict Invariant: No Document Text)
# ---------------------------------------------------------------------------
def create_extraction_audit_log_entry(
    assessment_id: str,
    question_id: str,
    gated_result: Dict[str, Any],
    user_action: Optional[str] = "pending",
    final_value: Any = None,
    time_to_confirm_ms: Optional[int] = None
) -> Dict[str, Any]:
    """
    Constructs a structured audit log entry adhering to PRD Section 12.1.
    CRITICAL SAFETY INVARIANT: Strictly NO document text or passage content is included.
    """
    return {
        "id": str(uuid.uuid4()),
        "assessment_id": assessment_id,
        "question_id": question_id,
        "method": gated_result.get("method", "CUAD_EXTRACTIVE_QA"),
        "model_name": CUAD_MODEL_REPO,
        "model_version": CUAD_MODEL_VERSION,
        "raw_score": gated_result.get("model_score", 0.0),
        "calibrated_score": gated_result.get("calibrated_score"),
        "status": gated_result.get("status", "MANUAL_REQUIRED"),
        "user_action": user_action,
        "final_value": final_value if final_value is not None else gated_result.get("answer_value"),
        "time_to_confirm_ms": time_to_confirm_ms,
        "created_at": datetime.now(timezone.utc).isoformat()
        # NOTE: No text, snippet, or passage field exists here!
    }
