import os
import logging
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

        # ── Parse immediately (Day 8 will move this to Celery) ──
        try:
            from .utils.pdf_parser import parse_contract_file
            result = parse_contract_file(file_path)

            contract.raw_text   = result['text']
            contract.page_count = result['page_count']
            contract.status     = 'done' if not result['error'] else 'error'
            contract.save()

            logger.info(
                f'Contract {contract.id} parsed via {result["method"]} '
                f'— {contract.page_count} pages, {len(contract.raw_text)} chars'
            )
        except Exception as e:
            logger.error(f'Parsing failed for contract {contract.id}: {e}')
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