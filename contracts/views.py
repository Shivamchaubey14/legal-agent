import os
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
        'contracts': contracts,
        'total':     contracts.count(),
        'high_risk': contracts.filter(risk_score__in=['high', 'critical']).count(),
        'done':      contracts.filter(status='done').count(),
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

        # ── Fire async Celery task ────────────────────────────
        from .tasks import process_contract
        process_contract.delay(contract.id)
        logger.info(f'Contract {contract.id} queued for async processing')

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
            'preview':    text[:2000],   # first 2000 chars
            'full_text':  text,
        })
        
# ── API: Dashboard stats ─────────────────────────────────────
class DashboardStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils.timezone import now
        from datetime import timedelta

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
    
class ContractFlagsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from contracts.models import ClauseFlag
        contract = get_object_or_404(Contract, pk=pk, user=request.user)
        flags    = ClauseFlag.objects.filter(contract=contract)

        data = [{
            'id':          f.id,
            'clause_type': f.clause_type,
            'risk_level':  f.risk_level,
            'clause_text': f.clause_text,
            'reason':      f.reason,
            'suggestion':  f.suggestion,
        } for f in flags]

        return Response({
            'success':    True,
            'contract_id': pk,
            'risk_score': contract.risk_score,
            'flags':      data,
            'count':      len(data),
        })