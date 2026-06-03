import logging
from contracts.models import Contract, ClauseFlag

logger = logging.getLogger(__name__)

# Weights per risk level
WEIGHTS = {
    'high':   3,
    'medium': 2,
    'low':    1,
}

# Score thresholds → overall risk label
THRESHOLDS = [
    (75, 'critical'),
    (50, 'high'),
    (25, 'medium'),
    (0,  'low'),
]


def compute_risk_score(contract: Contract) -> dict:
    """
    Weighted formula:
      high=3, medium=2, low=1
      Normalize to 0-100
      Map to Low / Medium / High / Critical
    """
    flags = ClauseFlag.objects.filter(contract=contract)

    if not flags.exists():
        return {
            'risk_score':    'low',
            'numeric_score': 0,
            'breakdown':     {'high': 0, 'medium': 0, 'low': 0},
            'total_flags':   0,
        }

    counts = {'high': 0, 'medium': 0, 'low': 0}
    for flag in flags:
        level = flag.risk_level.lower()
        if level in counts:
            counts[level] += 1

    weighted_sum = (
        counts['high']   * WEIGHTS['high']   +
        counts['medium'] * WEIGHTS['medium'] +
        counts['low']    * WEIGHTS['low']
    )

    # Max possible score if all flags were high
    max_score = flags.count() * WEIGHTS['high']
    numeric   = round((weighted_sum / max_score) * 100) if max_score > 0 else 0

    # Map to label
    risk_label = 'low'
    for threshold, label in THRESHOLDS:
        if numeric >= threshold:
            risk_label = label
            break

    logger.info(
        f'Contract {contract.id} score: {numeric}/100 → {risk_label} '
        f'(H:{counts["high"]} M:{counts["medium"]} L:{counts["low"]})'
    )

    return {
        'risk_score':    risk_label,
        'numeric_score': numeric,
        'breakdown':     counts,
        'total_flags':   flags.count(),
    }