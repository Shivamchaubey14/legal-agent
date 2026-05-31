from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .serializers import RegisterSerializer, LoginSerializer, UserSerializer


# ── Helper: generate token pair for a user ──────────────────
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }


# ── API: Register ────────────────────────────────────────────
class RegisterAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user   = serializer.save()
            tokens = get_tokens_for_user(user)
            return Response({
                'success': True,
                'message': 'Account created successfully.',
                'user':    UserSerializer(user).data,
                'tokens':  tokens,
            }, status=status.HTTP_201_CREATED)
        return Response({
            'success': False,
            'errors':  serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)


# ── API: Login ───────────────────────────────────────────────
class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'errors':  serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(
            request,
            username=serializer.validated_data['username'],
            password=serializer.validated_data['password'],
        )
        if not user:
            return Response({
                'success': False,
                'error':   'Invalid username or password.',
            }, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({
                'success': False,
                'error':   'Account is disabled.',
            }, status=status.HTTP_403_FORBIDDEN)

        # Also log in via session (so Django templates work too)
        login(request, user)
        tokens = get_tokens_for_user(user)

        return Response({
            'success':  True,
            'message':  f'Welcome back, {user.username}!',
            'user':     UserSerializer(user).data,
            'tokens':   tokens,
            'redirect': '/dashboard/',
        }, status=status.HTTP_200_OK)


# ── API: Logout ──────────────────────────────────────────────
class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except TokenError:
            pass  # token already invalid — that's fine
        logout(request)
        return Response({
            'success': True,
            'message': 'Logged out successfully.',
        }, status=status.HTTP_200_OK)


# ── API: Me (current user info) ──────────────────────────────
class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'success': True,
            'user':    UserSerializer(request.user).data,
        })


# ── Template views (render HTML pages) ──────────────────────
def login_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'login.html')


def register_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'register.html')


def logout_view(request):
    logout(request)
    return redirect('index')