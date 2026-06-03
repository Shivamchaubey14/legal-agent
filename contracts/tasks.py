import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_contract(self, contract_id: int) -> dict:
    """
    Full async pipeline:
      1. Parse PDF/DOCX → extract raw text
      2. Embed chunks   → store in ChromaDB
      3. Analyze        → detect risky clauses with AI agent
      4. Score          → compute overall risk score
      5. Save           → persist everything to DB

    This task is called after file upload so the HTTP
    response returns immediately and processing happens
    in the background.
    """
    from contracts.models import Contract

    try:
        contract = Contract.objects.get(id=contract_id)
    except Contract.DoesNotExist:
        logger.error(f'Contract {contract_id} not found')
        return {'success': False, 'error': 'Contract not found'}

    logger.info(f'Starting pipeline for contract {contract_id}: {contract.title}')
    contract.status = 'processing'
    contract.save()

    # ── Step 1: Parse ────────────────────────────────────────
    try:
        logger.info(f'[{contract_id}] Step 1: Parsing file')
        from contracts.utils.pdf_parser import parse_contract_file

        result = parse_contract_file(contract.file_path)

        if result['error']:
            raise Exception(f'Parse error: {result["error"]}')

        contract.raw_text   = result['text']
        contract.page_count = result['page_count']
        contract.save()

        logger.info(
            f'[{contract_id}] Parsed via {result["method"]} — '
            f'{result["page_count"]} pages, {len(result["text"])} chars'
        )
    except Exception as exc:
        logger.error(f'[{contract_id}] Parse failed: {exc}')
        contract.status = 'error'
        contract.save()
        raise self.retry(exc=exc)

    # ── Step 2: Embed ────────────────────────────────────────
    try:
        logger.info(f'[{contract_id}] Step 2: Embedding chunks')
        from contracts.utils.embedder import embed_contract

        embed_result = embed_contract(contract_id, contract.raw_text)

        if not embed_result['success']:
            raise Exception(f'Embed error: {embed_result["error"]}')

        logger.info(f'[{contract_id}] Embedded {embed_result["chunks"]} chunks')
    except Exception as exc:
        logger.error(f'[{contract_id}] Embed failed: {exc}')
        contract.status = 'error'
        contract.save()
        raise self.retry(exc=exc)

    # ── Step 3: Analyze ──────────────────────────────────────
    try:
        logger.info(f'[{contract_id}] Step 3: Running clause detection agent')
        from contracts.utils.agent        import run_clause_detection_agent
        from contracts.utils.clause_saver import save_clause_flags

        agent_result = run_clause_detection_agent(contract_id, contract.raw_text)

        if not agent_result['success']:
            raise Exception(f'Agent error: {agent_result["error"]}')

        saved = save_clause_flags(contract, agent_result['flags'])
        logger.info(f'[{contract_id}] Saved {saved} clause flags')

    except Exception as exc:
        logger.error(f'[{contract_id}] Analysis failed: {exc}')
        contract.status = 'error'
        contract.save()
        raise self.retry(exc=exc)

    # ── Step 4: Score ────────────────────────────────────────
    try:
        logger.info(f'[{contract_id}] Step 4: Computing risk score')
        from contracts.utils.scorer import compute_risk_score

        score_result      = compute_risk_score(contract)
        contract.risk_score = score_result['risk_score']
        contract.save()

        logger.info(
            f'[{contract_id}] Risk score: {score_result["risk_score"]} '
            f'(numeric: {score_result["numeric_score"]})'
        )
    except Exception as exc:
        logger.error(f'[{contract_id}] Scoring failed: {exc}')
        # Don't retry for scoring — just mark done without score

    # ── Done ─────────────────────────────────────────────────
    contract.status = 'done'
    contract.save()

    logger.info(f'[{contract_id}] Pipeline complete.')

    return {
        'success':     True,
        'contract_id': contract_id,
        'page_count':  contract.page_count,
        'risk_score':  contract.risk_score,
        'flags':       agent_result.get('total_flags', 0),
    }