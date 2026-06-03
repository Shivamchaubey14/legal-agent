import os
import re
import logging
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404

logger = logging.getLogger(__name__)
from django.contrib.auth.decorators import login_required
from django.utils.text import get_valid_filename

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status

from .models import Contract
from .serializers import ContractSerializer


# ── Allowed file types ───────────────────────────────────────
ALLOWED_EXTENSIONS = {'.pdf', '.docx'}
MAX_FILE_SIZE_MB   = 20
MAX_FILE_SIZE_B    = MAX_FILE_SIZE_MB * 1024 * 1024


# ── Template views ───────────────────────────────────────────
def index(request):
    return render(request, 'index.html')


@login_required
def dashboard(request):
    contracts = Contract.objects.filter(user=request.user)
    return render(request, 'dashboard.html', {
        'contracts':  contracts,
        'total':      contracts.count(),
        'high_risk':  contracts.filter(risk_score__in=['high', 'critical']).count(),
        'done':       contracts.filter(status='done').count(),
        'processing': contracts.filter(status='processing').count(),
        'pending':    contracts.filter(status='pending').count(),
        'errors':     contracts.filter(status='error').count(),
    })


@login_required
def upload_page(request):
    return render(request, 'upload.html')


# ── API: List contracts ──────────────────────────────────────
class ContractListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        contracts  = Contract.objects.filter(user=request.user)
        serializer = ContractSerializer(contracts, many=True)
        return Response({
            'success':   True,
            'count':     contracts.count(),
            'contracts': serializer.data,
        })


# ── API: Upload contract ─────────────────────────────────────
class ContractUploadAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get('file')

        # ── Validation ───────────────────────────────────────
        if not file:
            return Response({
                'success': False,
                'error':   'No file provided.',
            }, status=status.HTTP_400_BAD_REQUEST)

        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return Response({
                'success': False,
                'error':   'Only PDF and DOCX files are allowed.',
            }, status=status.HTTP_400_BAD_REQUEST)

        if file.size > MAX_FILE_SIZE_B:
            return Response({
                'success': False,
                'error':   f'File too large. Maximum size is {MAX_FILE_SIZE_MB}MB.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # ── Save file to media/contracts/<user_id>/ ──────────
        title     = request.data.get('title', '').strip()
        if not title:
            title = os.path.splitext(file.name)[0].replace('_', ' ').replace('-', ' ').title()

        safe_name  = get_valid_filename(file.name)
        upload_dir = os.path.join('contracts', str(request.user.id))
        full_dir   = os.path.join('media', upload_dir)
        os.makedirs(full_dir, exist_ok=True)

        file_path = os.path.join(full_dir, safe_name)

        # Write file in chunks (handles large files)
        with open(file_path, 'wb+') as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        # ── Create Contract record ───────────────────────────
        contract = Contract.objects.create(
            user      = request.user,
            title     = title,
            file_path = file_path,
            status    = 'processing',
        )

        # ── Trigger async Celery pipeline ────────────────────
        try:
            from .tasks import process_contract
            process_contract.delay(contract.id)
            logger.info(f'Queued contract {contract.id} for async processing')

        except Exception as e:
            # If Redis/Celery is unavailable, fall back to sync
            logger.warning(f'Celery unavailable, running sync: {e}')

            try:
                from .utils.pdf_parser import parse_contract_file
                from .utils.embedder   import embed_contract

                result = parse_contract_file(file_path)

                contract.raw_text   = result['text']
                contract.page_count = result['page_count']

                if result.get('error'):
                    contract.status = 'error'
                    contract.save()
                else:
                    embed_contract(contract.id, result['text'])
                    contract.status = 'done'
                    contract.save()

            except Exception as e2:
                logger.error(f'Sync fallback failed: {e2}')
                contract.status = 'error'
                contract.save()

        return Response({
            'success':  True,
            'message':  'Contract uploaded and parsed successfully.',
            'contract': ContractSerializer(contract).data,
            'redirect': '/dashboard/',
        }, status=status.HTTP_201_CREATED)


# ── API: Contract detail + delete ───────────────────────────
class ContractDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk, user=request.user)
        return Response({
            'success':  True,
            'contract': ContractSerializer(contract).data,
        })

    def delete(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk, user=request.user)

        # Delete embeddings from ChromaDB
        try:
            from .utils.embedder import delete_contract_embeddings
            delete_contract_embeddings(contract.id)
        except Exception as e:
            logger.warning(f'ChromaDB cleanup failed for contract {contract.id}: {e}')

        # Delete file from disk
        if contract.file_path and os.path.exists(contract.file_path):
            os.remove(contract.file_path)

        contract.delete()
        return Response({
            'success': True,
            'message': 'Contract deleted.',
        }, status=status.HTTP_204_NO_CONTENT)


# ── API: Contract status polling ─────────────────────────────
class ContractStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk, user=request.user)
        return Response({
            'success':    True,
            'id':         contract.id,
            'status':     contract.status,
            'risk_score': contract.risk_score,
            'page_count': contract.page_count,
            'title':      contract.title,
        })


# ── API: Raw text preview ────────────────────────────────────
class ContractTextAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk, user=request.user)
        text     = contract.raw_text or ''
        return Response({
            'success':    True,
            'id':         contract.id,
            'title':      contract.title,
            'page_count': contract.page_count,
            'char_count': len(text),
            'preview':    text[:2000],
            'full_text':  text,
        })


# ── API: Dashboard stats ─────────────────────────────────────
class DashboardStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils.timezone import now

        contracts  = Contract.objects.filter(user=request.user)
        this_month = contracts.filter(
            created_at__month=now().month,
            created_at__year=now().year,
        ).count()

        return Response({
            'success':             True,
            'avg_risk_score':      '–',
            'this_month':          this_month,
            'avg_processing_time': '–',
            'pending_qa':          0,
        })


# ── API: Embed a contract manually ──────────────────────────
class ContractEmbedAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk, user=request.user)

        if not contract.raw_text:
            return Response({
                'success': False,
                'error':   'No text to embed. Parse the contract first.',
            }, status=status.HTTP_400_BAD_REQUEST)

        from .utils.embedder import embed_contract
        result = embed_contract(contract.id, contract.raw_text)

        return Response({
            'success': result['success'],
            'chunks':  result['chunks'],
            'error':   result['error'],
        })


# ── API: Semantic search within a contract ───────────────────
class ContractSearchAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk, user=request.user)
        query    = request.data.get('query', '').strip()

        if not query:
            return Response({
                'success': False,
                'error':   'Query is required.',
            }, status=status.HTTP_400_BAD_REQUEST)

        from .utils.embedder import query_contract
        chunks = query_contract(contract.id, query, top_k=5)

        return Response({
            'success': True,
            'query':   query,
            'results': chunks,
            'count':   len(chunks),
        })


# ── API: ChromaDB stats ──────────────────────────────────────
class EmbedStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .utils.embedder import get_collection_stats
        stats = get_collection_stats()
        return Response({'success': True, **stats})


# ── API: Get clause flags for a contract ─────────────────────
class ContractFlagsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from .models import ClauseFlag

        contract = get_object_or_404(Contract, pk=pk, user=request.user)
        flags    = ClauseFlag.objects.filter(contract=contract)

        high_count   = flags.filter(risk_level__in=['high', 'critical']).count()
        medium_count = flags.filter(risk_level='medium').count()
        low_count    = flags.filter(risk_level='low').count()

        flag_data = []
        for flag in flags:
            flag_data.append({
                'id':          flag.id,
                'clause_type': flag.clause_type,
                'risk_level':  flag.risk_level,
                'clause_text': flag.clause_text,
                'reason':      flag.reason,
                'suggestion':  flag.suggestion,
                'page_number': flag.page_number,
                'start_char':  flag.start_char,
                'end_char':    flag.end_char,
                'created_at':  flag.created_at,
            })

        return Response({
            'success': True,
            'contract': {
                'id':         contract.id,
                'title':      contract.title,
                'status':     contract.status,
                'risk_score': contract.risk_score,
                'page_count': contract.page_count,
                'created_at': contract.created_at,
            },
            'summary': {
                'total_flags': flags.count(),
                'high_risk':   high_count,
                'medium_risk': medium_count,
                'low_risk':    low_count,
            },
            'flags': flag_data,
        })


# ── API: Contract review (for JS fetch) ─────────────────────
class ContractReviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk, user=request.user)
        flags    = contract.clause_flags.all()

        return Response({
            'success':    True,
            'contract_id': contract.id,
            'title':      contract.title,
            'status':     contract.status,
            'risk_score': contract.risk_score,
            'page_count': contract.page_count,
            'raw_text':   contract.raw_text,
            'flags': [
                {
                    'id':          f.id,
                    'type':        f.clause_type,
                    'risk':        f.risk_level,
                    'text':        f.clause_text,
                    'reason':      f.reason,
                    'suggestion':  f.suggestion,
                    'page_number': f.page_number,
                }
                for f in flags
            ]
        })


# ── Template view: Contract review page ─────────────────────
@login_required
def contract_review_page(request, pk):
    from .models import ClauseFlag
    from .utils.agent import clean_ocr_text, strip_stamp_paper_header

    contract = get_object_or_404(Contract, pk=pk, user=request.user)
    flags    = ClauseFlag.objects.filter(contract=contract)

    # Clean the raw_text before showing in template
    raw_text = contract.raw_text or ''
    raw_text = clean_ocr_text(raw_text)
    raw_text = strip_stamp_paper_header(raw_text)

    flags_data = []
    for flag in flags:
        flags_data.append({
            'type':        flag.clause_type,
            'risk':        flag.risk_level,
            'text':        flag.clause_text,
            'reason':      flag.reason,
            'suggestion':  flag.suggestion,
            'page_number': flag.page_number,
        })

    return render(request, 'contract_review.html', {
        'contract':  contract,
        'raw_text':  raw_text,
        'flags':     flags_data,
    })


# ── API: Run clause detection agent ─────────────────────────
class ContractAnalyzeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk, user=request.user)

        if not contract.raw_text:
            return Response({
                'success': False,
                'error':   'Contract has no text. Upload and parse first.',
            }, status=status.HTTP_400_BAD_REQUEST)

        contract.status = 'processing'
        contract.save()

        try:
            from .models          import ClauseFlag
            from .serializers     import ClauseFlagSerializer
            from .utils.agent        import run_clause_detection_agent
            from .utils.clause_saver import save_clause_flags
            from .utils.risk_scorer  import apply_risk_score

            result = run_clause_detection_agent(contract.id, contract.raw_text)

            if not result['success']:
                contract.status = 'error'
                contract.save()
                return Response({
                    'success': False,
                    'error':   result['error'],
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            saved = save_clause_flags(contract, result['flags'])

            # ── Day 11: compute and apply risk score ─────────
            from .utils.risk_scorer import apply_risk_score
            score_result = apply_risk_score(contract)  # sets status='done' and saves

            from .models import ClauseFlag
            flags = ClauseFlag.objects.filter(contract=contract)

            return Response({
                'success':     True,
                'total_flags': saved,
                'risk_score':  score_result['label'],
                'risk_value':  score_result['score'],
                'breakdown':   score_result['breakdown'],
                'flags':       ClauseFlagSerializer(flags, many=True).data,
            })

        except Exception as e:
            logger.error(f'Agent error for contract {pk}: {e}')
            contract.status = 'error'
            contract.save()
            return Response({
                'success': False,
                'error':   str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)           
            
# ── API: Bulk Export ZIP ─────────────────────────────────────
class BulkExportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import zipfile
        import io
        from django.http import HttpResponse

        ids = request.data.get('ids', [])
        if not ids:
            return Response({'success': False, 'error': 'No contract IDs provided.'}, status=400)

        contracts = Contract.objects.filter(pk__in=ids, user=request.user)
        if not contracts.exists():
            return Response({'success': False, 'error': 'No contracts found.'}, status=404)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for contract in contracts:
                if contract.raw_text:
                    safe_title = re.sub(r'[^\w\s-]', '', contract.title)[:50]
                    filename   = f"{safe_title}_{contract.id}.txt"
                    zf.writestr(filename, contract.raw_text)
                if contract.file_path and os.path.exists(contract.file_path):
                    orig_filename = os.path.basename(contract.file_path)
                    zf.write(contract.file_path, f"originals/{orig_filename}")

        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="contracts_export.zip"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return response


# ── API: Bulk Re-run Analysis ────────────────────────────────
class BulkRerunAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'success': False, 'error': 'No contract IDs provided.'}, status=400)

        contracts = Contract.objects.filter(pk__in=ids, user=request.user)
        queued    = []
        failed    = []

        for contract in contracts:
            if not contract.raw_text:
                failed.append(contract.id)
                continue
            try:
                contract.status = 'processing'
                contract.save()
                from .tasks import process_contract
                process_contract.delay(contract.id)
                queued.append(contract.id)
            except Exception:
                # Sync fallback
                try:
                    from .utils.agent        import run_clause_detection_agent
                    from .utils.clause_saver import save_clause_flags
                    contract.clause_flags.all().delete()
                    result = run_clause_detection_agent(contract.id, contract.raw_text)
                    if result['success']:
                        save_clause_flags(contract, result['flags'])
                        contract.status = 'done'
                    else:
                        contract.status = 'error'
                    contract.save()
                    queued.append(contract.id)
                except Exception as e2:
                    logger.error(f'Re-run failed for {contract.id}: {e2}')
                    contract.status = 'error'
                    contract.save()
                    failed.append(contract.id)

        return Response({
            'success': True,
            'queued':  queued,
            'failed':  failed,
            'message': f'{len(queued)} contract(s) queued for re-analysis.',
        })


# ── API: Bulk Assign ─────────────────────────────────────────
class BulkAssignAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        ids      = request.data.get('ids', [])
        assignee = request.data.get('assignee', '').strip()

        if not ids:
            return Response({'success': False, 'error': 'No contract IDs provided.'}, status=400)
        if not assignee:
            return Response({'success': False, 'error': 'Assignee is required.'}, status=400)

        contracts = Contract.objects.filter(pk__in=ids, user=request.user)

        # Store assignee as a note in each contract's title metadata
        # (extend your Contract model with an `assignee` field later)
        assigned = []
        for contract in contracts:
            # For now tag the assignee in a notes field if it exists,
            # or just track in response — extend model as needed
            assigned.append({
                'id':    contract.id,
                'title': contract.title,
            })

        return Response({
            'success':  True,
            'assignee': assignee,
            'assigned': assigned,
            'message':  f'{len(assigned)} contract(s) assigned to {assignee}.',
        })


# ── API: Bulk Delete ─────────────────────────────────────────
class BulkDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'success': False, 'error': 'No contract IDs provided.'}, status=400)

        contracts = Contract.objects.filter(pk__in=ids, user=request.user)
        deleted   = []

        for contract in contracts:
            # Delete ChromaDB embeddings
            try:
                from .utils.embedder import delete_contract_embeddings
                delete_contract_embeddings(contract.id)
            except Exception as e:
                logger.warning(f'ChromaDB cleanup failed for {contract.id}: {e}')

            # Delete file from disk
            if contract.file_path and os.path.exists(contract.file_path):
                try:
                    os.remove(contract.file_path)
                except Exception as e:
                    logger.warning(f'File delete failed for {contract.id}: {e}')

            deleted.append(contract.id)
            contract.delete()

        return Response({
            'success': True,
            'deleted': deleted,
            'message': f'{len(deleted)} contract(s) deleted.',
        })