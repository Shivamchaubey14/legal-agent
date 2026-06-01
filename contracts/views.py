from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Contract
from .serializers import ContractSerializer


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


# ── API: List all contracts for current user ─────────────────
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


# ── API: Single contract detail ──────────────────────────────
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
        contract.delete()
        return Response({
            'success': True,
            'message': 'Contract deleted.',
        }, status=status.HTTP_204_NO_CONTENT)