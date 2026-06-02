import logging
from celery import shared_task
from contracts.models import Contract
from contracts.utils.pdf_parser import parse_contract_file
from contracts.utils.embedder import embed_contract

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_contract(self, contract_id: int) -> dict:
    """
    Full async pipeline for a newly uploaded contract.
    Steps: parse → embed → (analyze in Day 9)
    """
    try:
        contract = Contract.objects.get(id=contract_id)
    except Contract.DoesNotExist:
        logger.error(f'Contract {contract_id} not found')
        return {'success': False, 'error': 'Contract not found'}

    try:
        # ── Step 1: Parse ──────────────────────────────
        contract.status = 'processing'
        contract.save(update_fields=['status'])

        logger.info(f'[Task] Parsing contract {contract_id}')
        parse_result = parse_contract_file(contract.file_path)

        if parse_result['method'] == 'failed' or not parse_result['text'].strip():
            contract.status = 'error'
            contract.save(update_fields=['status'])
            return {'success': False, 'error': 'PDF parsing failed — no text extracted'}

        contract.raw_text   = parse_result['text']
        contract.page_count = parse_result['page_count']
        contract.save(update_fields=['raw_text', 'page_count'])

        # ── Step 2: Embed ──────────────────────────────
        logger.info(f'[Task] Embedding contract {contract_id}')
        embed_result = embed_contract(contract_id, contract.raw_text)

        if not embed_result.get('success'):
            contract.status = 'error'
            contract.save(update_fields=['status'])
            return {'success': False, 'error': 'Embedding failed'}

        # ── Step 3: Mark done (analysis added Day 9) ──
        contract.status = 'done'
        contract.save(update_fields=['status'])

        logger.info(f'[Task] Contract {contract_id} processed successfully')
        return {
            'success':    True,
            'contract_id': contract_id,
            'method':     parse_result['method'],
            'pages':      parse_result['page_count'],
            'chunks':     embed_result.get('chunks', 0),
        }

    except Exception as exc:
        logger.error(f'[Task] Contract {contract_id} failed: {exc}')
        try:
            contract.status = 'error'
            contract.save(update_fields=['status'])
        except Exception:
            pass
        # Retry with exponential backoff: 60s, 120s, 240s
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))