import logging
from contracts.models import Contract, ClauseFlag

logger = logging.getLogger(__name__)


def save_clause_flags(contract: Contract, flags: list) -> int:
    """
    Save detected clause flags to the database.
    Clears existing flags before saving new ones.
    Returns count of saved flags.
    """
    # Clear existing flags for this contract
    ClauseFlag.objects.filter(contract=contract).delete()

    saved = 0
    for flag in flags:
        try:
            ClauseFlag.objects.create(
                contract    = contract,
                clause_type = flag.get('clause_type', 'General'),
                clause_text = flag.get('clause_text', ''),
                risk_level  = flag.get('risk_level',  'medium'),
                reason      = flag.get('reason',      ''),
                suggestion  = flag.get('suggestion',  ''),
                redline     = flag.get('redline',     ''),   # ← add this
                page_number = flag.get('page_number', 1),
                start_char  = 0,
                end_char    = 0,
            )
            saved += 1
        except Exception as e:
            logger.error(f'Error saving flag: {e}')

    logger.info(f'Saved {saved} clause flags for contract {contract.id}')
    return saved