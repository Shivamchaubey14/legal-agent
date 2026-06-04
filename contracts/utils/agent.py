import os
import re
import json
import logging
from typing import TypedDict, Annotated
import operator

from openai import OpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from .embedder import query_contract, query_playbooks

logger = logging.getLogger(__name__)

# ── Grok client ──────────────────────────────────────────────
client = OpenAI(
    api_key=os.getenv('GROQ_API_KEY', ''),
    base_url="https://api.groq.com/openai/v1",  # ← Groq not xAI
)

# ── Clause types we detect ───────────────────────────────────
CLAUSE_TYPES = [
    'Termination',
    'Liability',
    'Indemnification',
    'Intellectual Property',
    'Payment',
    'Confidentiality',
    'Governing Law',
    'Non-Compete',
    'Non-Solicitation',
    'Data Privacy',
    'Auto-Renewal',
    'Service Level Agreement',
]

# ── Risk levels ───────────────────────────────────────────────
RISK_LEVELS = ['low', 'medium', 'high']

# ── Contract start markers (to strip stamp paper garbage) ────
CONTRACT_START_MARKERS = [
    'TUS LEASE AGREEMENT',      # your OCR variant — most specific, check first
    'THIS LEASE AGRERMENT',
    'THIS LEASE AGREEMENT',
    'LEASE AGREEMENT',
    'THIS Contract agreement',
    'This Contract agreement',
    'THIS AGREEMENT',
    'This Agreement is made',
    'THIS DEED OF AGREEMENT',
    'This Deed of Agreement',
    'THIS DEED WITNESSETH',
    'THIS SERVICE AGREEMENT',
    'This Service Agreement',
    'EMPLOYMENT AGREEMENT',
    'Employment Agreement',
    'CONSULTANCY AGREEMENT',
    'Consultancy Agreement',
    'NOW THEREFORE',
    'WITNESSETH',
    'A. WHEREAS',               # fallback — at least gets recitals
    'WHEREAS the Lessor',
    'WHEREAS the Parties',
]


# ── Agent state ───────────────────────────────────────────────
class AgentState(TypedDict):
    contract_id:   int
    contract_text: str
    clause_flags:  list
    current_chunk: str
    messages:      list
    done:          bool


# ── Tool: search contract ────────────────────────────────────
def search_contract_tool(contract_id: int, query: str) -> list:
    """Search within a contract for relevant clauses."""
    results = query_contract(contract_id, query, top_k=3)
    return results


# ── Tool: search playbook ────────────────────────────────────
def search_playbook_tool(query: str) -> list:
    """Search legal playbooks for standard clause language."""
    results = query_playbooks(query, top_k=3)
    return results


# ── Clean OCR garbage lines ──────────────────────────────────
def clean_ocr_text(text: str) -> str:
    """Remove lines that are mostly non-alphanumeric (OCR garbage)."""
    if not text:
        return text

    lines         = text.split('\n')
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append('')
            continue

        alpha_count = sum(1 for c in stripped if c.isalnum() or c in ' .,;:()\'-"/')
        ratio       = alpha_count / len(stripped) if stripped else 0

        if ratio >= 0.40:
            cleaned_lines.append(line)

    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    text = re.sub(r'[ \t]{3,}', ' ', text)
    return text.strip()


# ── Strip stamp paper header ─────────────────────────────────
def strip_stamp_paper_header(text: str) -> str:
    if not text:
        return text

    for marker in CONTRACT_START_MARKERS:
        idx = text.find(marker)
        if idx > 100:          # ← lowered from 300 to 100
            logger.info(f'Stripped {idx} chars at marker: "{marker}"')
            return text[idx:]

    return text

def _call_with_retry(fn, max_retries: int = 3, backoff: float = 2.0):
    """
    Call fn() with exponential backoff on rate-limit or transient errors.
    Raises the last exception if all retries fail.
    """
    import time
    last_exc = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            err_str  = str(e).lower()
            # Retry on rate limit or 5xx server errors
            if any(k in err_str for k in ('rate limit', '429', '503', '502', 'timeout', 'connection')):
                wait = backoff ** attempt
                logger.warning(f'API error (attempt {attempt+1}/{max_retries}), retrying in {wait}s: {e}')
                time.sleep(wait)
            else:
                raise   # Non-retryable error — fail immediately
    raise last_exc

# ── Core analysis function ───────────────────────────────────
def analyze_chunk(contract_id: int, chunk: str, chunk_index: int) -> list:
    """
    Send a contract chunk to Grok for clause detection.
    Returns list of detected clause flags.
    """

    system_prompt = """You are a legal contract analysis expert. 
Your job is to analyze contract text and identify risky clauses.

For each risky clause you find, return a JSON object with:
- clause_type: one of [Termination, Liability, Indemnification, Intellectual Property, 
  Payment, Confidentiality, Governing Law, Non-Compete, Non-Solicitation, 
  Data Privacy, Auto-Renewal, Service Level Agreement]
- clause_text: the exact problematic text (max 300 chars)
- risk_level: low, medium, or high
- reason: why this clause is risky (1-2 sentences)
- suggestion: how to improve it (1-2 sentences)
- page_number: estimate based on position (use 1 if unknown)

Return ONLY a valid JSON array. If no risky clauses found, return [].
Do not include any explanation outside the JSON."""

    user_prompt = f"""Analyze this contract section for risky clauses:

{chunk}

Return a JSON array of flagged clauses."""

    try:
        response = _call_with_retry(lambda: client.chat.completions.create(
            model="llama-3.1-8b-instant",   # best free Groq model
            max_tokens = 2000,
            messages   = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user',   'content': user_prompt},
            ],
        ))

        raw = response.choices[0].message.content.strip()

        # Debug — visible in Django server terminal
        print(f"\nDEBUG GROK chunk {chunk_index}:\n{raw[:500]}\n")

        # Clean up response — strip markdown code blocks if present
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        raw = raw.strip()

        flags = json.loads(raw)
        if not isinstance(flags, list):
            flags = []

        # Validate and normalize each flag
        validated = []
        for flag in flags:
            if not isinstance(flag, dict):
                continue
            validated.append({
                'clause_type':  str(flag.get('clause_type',  'General')),
                'clause_text':  str(flag.get('clause_text',  ''))[:500],
                'risk_level':   str(flag.get('risk_level',   'medium')).lower(),
                'reason':       str(flag.get('reason',       '')),
                'suggestion':   str(flag.get('suggestion',   '')),
                'page_number':  int(flag.get('page_number',  1)),
                'chunk_index':  chunk_index,
            })

        logger.info(f'Chunk {chunk_index}: found {len(validated)} flags')
        return validated

    except json.JSONDecodeError as e:
        logger.error(f'JSON parse error on chunk {chunk_index}: {e}')
        print(f"DEBUG JSON ERROR chunk {chunk_index}: {e}\nRaw was: {raw[:300]}")
        return []
    except Exception as e:
        logger.error(f'Grok API error on chunk {chunk_index}: {e}')
        return []


# ── Playbook comparison ──────────────────────────────────────
def compare_with_playbook(clause_type: str, clause_text: str) -> str:
    """
    Compare a flagged clause against the playbook standard.
    Returns enhanced suggestion grounded in playbook.
    """
    playbook_results = search_playbook_tool(
        f'{clause_type} clause risk: {clause_text[:100]}'
    )

    if not playbook_results:
        return ''

    playbook_context = '\n\n'.join([r['text'][:400] for r in playbook_results[:2]])

    prompt = f"""You are a legal expert. Compare this contract clause against the standard playbook.

CONTRACT CLAUSE ({clause_type}):
{clause_text[:300]}

STANDARD PLAYBOOK:
{playbook_context}

In 2 sentences, explain specifically what is missing or risky compared to the standard, 
and what exact language should be added or changed. Be specific and actionable."""

    try:
        response = _call_with_retry(lambda: client.chat.completions.create(
            model="llama-3.1-8b-instant",   # best free Groq model
            max_tokens = 300,
            messages   = [{'role': 'user', 'content': prompt}],
        ))
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f'Playbook comparison error: {e}')
        return ''
    
# ── Risk scoring ──────────────────────────────────────────────
RISK_WEIGHTS = {
    'high':   3,
    'medium': 2,
    'low':    1,
}

def score_clause_risk(clause_type: str, clause_text: str, current_risk: str) -> str:
    """
    Re-evaluate and confirm/upgrade the risk level using a dedicated scoring call.
    Returns a validated risk level: 'low', 'medium', or 'high'.
    """
    prompt = f"""You are a senior legal risk analyst. Score the risk level of this clause.

CLAUSE TYPE: {clause_type}
CLAUSE TEXT: {clause_text[:300]}

Score as one of: low, medium, high

Criteria:
- high: clause is one-sided, waives critical rights, unlimited liability, immediate termination without notice, unfair IP assignment
- medium: clause is imbalanced but negotiable, short payment windows, vague scope, weak confidentiality
- low: clause is standard with minor concerns, common boilerplate, short notice periods

Respond with ONLY one word: low, medium, or high"""

    try:
        response = _call_with_retry(lambda: client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=10,
            messages=[{'role': 'user', 'content': prompt}],
        ))
        score = response.choices[0].message.content.strip().lower()
        if score not in ('low', 'medium', 'high'):
            return current_risk
        return score
    except Exception as e:
        logger.error(f'Risk scoring error: {e}')
        return current_risk


# ── Redline suggestion generator ─────────────────────────────
def generate_redline(clause_type: str, clause_text: str) -> str:
    """
    Generate a specific redlined (rewritten) alternative for a risky clause.
    Returns suggested replacement language.
    """
    prompt = f"""You are a contract lawyer. Rewrite this risky clause with balanced, standard language.

CLAUSE TYPE: {clause_type}
ORIGINAL TEXT: {clause_text[:300]}

Write ONLY the improved clause text (2-4 sentences). 
Make it balanced and fair to both parties. 
Start directly with the clause language — no preamble."""

    try:
        response = _call_with_retry(lambda: client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=250,
            messages=[{'role': 'user', 'content': prompt}],
        ))
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f'Redline generation error: {e}')
        return ''


# ── Main agent function ──────────────────────────────────────
def run_clause_detection_agent(contract_id: int, raw_text: str) -> dict:
    """
    Main entry point. Analyzes a full contract and returns all flags.

    Returns:
        {
            'success':     bool,
            'flags':       list of clause flags,
            'total_flags': int,
            'error':       str | None
        }
    """
    if not raw_text or not raw_text.strip():
        return {
            'success':     False,
            'flags':       [],
            'total_flags': 0,
            'error':       'No contract text to analyze',
        }

    logger.info(f'Starting clause detection for contract {contract_id}')

    # ── Step 1: Clean OCR garbage lines ─────────────────────
    clean_text = clean_ocr_text(raw_text)

    # ── Step 2: Strip stamp paper header ────────────────────
    clean_text = strip_stamp_paper_header(clean_text)

    # ── Debug: confirm clean text ────────────────────────────
    print(f"\nDEBUG: Clean text length: {len(clean_text)}")
    print(f"DEBUG: Clean text preview:\n{clean_text[:400]}\n")

    if not clean_text.strip():
        return {
            'success':     False,
            'flags':       [],
            'total_flags': 0,
            'error':       'Contract text is empty after cleaning',
        }

    # ── Step 3: Split into chunks for analysis ───────────────
    from .embedder import chunk_text
    chunks    = chunk_text(clean_text, chunk_size=600, overlap=60)
    all_flags = []
    seen_texts = set()  # deduplicate similar flags

    print(f"DEBUG: Total chunks to analyze: {len(chunks)}")

    for i, chunk in enumerate(chunks):
        logger.info(f'Analyzing chunk {i+1}/{len(chunks)}')
        flags = analyze_chunk(contract_id, chunk, i)

        for flag in flags:
            key = f"{flag['clause_type']}:{flag['clause_text'][:80]}"
            if key in seen_texts:
                continue
            seen_texts.add(key)

            # ── Day 10 additions ─────────────────────────────

            # 1. Re-score risk level with dedicated scorer
            flag['risk_level'] = score_clause_risk(
                flag['clause_type'],
                flag['clause_text'],
                flag['risk_level'],
            )

            # 2. Generate redline suggestion
            redline = generate_redline(flag['clause_type'], flag['clause_text'])
            if redline:
                flag['redline'] = redline

            # 3. Enhance suggestion with playbook comparison (existing)
            if flag['clause_type'] and flag['clause_text']:
                enhanced = compare_with_playbook(
                    flag['clause_type'],
                    flag['clause_text'],
                )
                if enhanced:
                    flag['suggestion'] = enhanced

            all_flags.append(flag)

    logger.info(
        f'Contract {contract_id} analysis complete: '
        f'{len(all_flags)} flags across {len(chunks)} chunks'
    )

    return {
        'success':     True,
        'flags':       all_flags,
        'total_flags': len(all_flags),
        'error':       None,
    }