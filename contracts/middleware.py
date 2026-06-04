import logging
import re

logger = logging.getLogger(__name__)

# Paths that contain a contract PK and must be ownership-checked
# Matches: /api/contracts/42/... or /contracts/42/review/
_CONTRACT_PK_RE = re.compile(r'^/(?:api/)?contracts/(\d+)/')


class OwnershipMiddleware:
    """
    Middleware that logs suspicious cross-ownership access attempts.
    Actual ownership enforcement is done in views via get_object_or_404,
    but this layer catches and logs anomalies centrally.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Log 404s on contract URLs for authenticated users — could be probing
        if (response.status_code == 404
                and request.user.is_authenticated
                and _CONTRACT_PK_RE.match(request.path)):
            logger.warning(
                f'Ownership/404: user={request.user.username} '
                f'path={request.path} method={request.method} '
                f'ip={_get_ip(request)}'
            )

        return response


def _get_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')