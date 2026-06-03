import logging
from contracts.models import Contract, ClauseFlag

logger = logging.getLogger(__name__)

# ── Weights ───────────────────────────────────────────────────
RISK_WEIGHTS = {
    'high':   3,
    'medium': 2,
    'low':    1,
}

# ── Clause type multipliers (some clause types are more dangerous) ──
CLAUSE_TYPE_MULTIPLIERS = {
    'Indemnification':      1.4,
    'Liability':            1.3,
    'Termination':          1.2,
    'Intellectual Property': 1.2,
    'Non-Compete':          1.1,
    'Data Privacy':         1.1,
    'Payment':              1.0,
    'Confidentiality':      1.0,
    'Governing Law':        0.8,
    'Auto-Renewal':         0.9,
    'Non-Solicitation':     0.9,
    'Service Level Agreement': 1.0,
}


def compute_risk_score(contract: Contract) -> dict:
    """
    Compute overall risk score for a contract from its ClauseFlags.

    Scoring formula:
      1. For each flag: base_weight × clause_type_multiplier
      2. Sum all weighted scores
      3. Normalise to 0–100 against a ceiling
      4. Map to label: Low / Medium / High / Critical

    Returns:
        {
            'score':       int (0-100),
            'label':       str ('low' | 'medium' | 'high' | 'critical'),
            'breakdown':   dict,
            'total_flags': int,
        }
    """
    flags = ClauseFlag.objects.filter(contract=contract)
    total = flags.count()

    if total == 0:
        return {
            'score':       0,
            'label':       'low',
            'breakdown':   {'high': 0, 'medium': 0, 'low': 0},
            'total_flags': 0,
        }

    # ── Count by risk level ───────────────────────────────────
    high_count   = flags.filter(risk_level='high').count()
    medium_count = flags.filter(risk_level='medium').count()
    low_count    = flags.filter(risk_level='low').count()

    # ── Weighted score ────────────────────────────────────────
    weighted_sum = 0.0
    for flag in flags:
        base       = RISK_WEIGHTS.get(flag.risk_level, 1)
        multiplier = CLAUSE_TYPE_MULTIPLIERS.get(flag.clause_type, 1.0)
        weighted_sum += base * multiplier

    # ── Normalise to 0–100 ────────────────────────────────────
    # Ceiling = every flag is high-risk indemnification (3 × 1.4 = 4.2 per flag)
    ceiling    = total * 4.2
    normalized = min(100, int((weighted_sum / ceiling) * 100))

    # ── Map to label ──────────────────────────────────────────
    if normalized >= 75:
        label = 'critical'
    elif normalized >= 50:
        label = 'high'
    elif normalized >= 25:
        label = 'medium'
    else:
        label = 'low'

    logger.info(
        f'Contract {contract.id} risk: {normalized}/100 ({label}) '
        f'— {high_count}H {medium_count}M {low_count}L across {total} flags'
    )

    return {
        'score':     normalized,
        'label':     label,
        'breakdown': {
            'high':   high_count,
            'medium': medium_count,
            'low':    low_count,
        },
        'total_flags': total,
    }


def apply_risk_score(contract: Contract) -> dict:
    """
    Compute and save the risk score to the contract.
    Sets status to 'done'.
    Returns the score dict.
    """
    result = compute_risk_score(contract)

    contract.risk_score = result['label']
    contract.status     = 'done'
    contract.save(update_fields=['risk_score', 'status'])

    logger.info(f'Contract {contract.id} finalised: {result["label"]} ({result["score"]}/100)')
    return result