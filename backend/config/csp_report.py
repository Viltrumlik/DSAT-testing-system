from __future__ import annotations

import json
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger("security.csp")


@method_decorator(csrf_exempt, name="dispatch")
class CSPReportView(APIView):
    """
    Browser `report-uri` / CSP Reporting API sink. Log-only; used during report-only → enforce.
    """

    permission_classes: list = []
    authentication_classes: list = []

    def post(self, request, *args, **kwargs):
        try:
            data = getattr(request, "data", None)
            if data:
                body = data
            else:
                body = json.loads((request.body or b"{}").decode("utf-8", errors="replace") or "{}")
        except Exception:
            body = {"raw": (request.body or b"")[:4000].decode("utf-8", errors="replace")}
        try:
            logger.warning("csp_violation %s", json.dumps(body, default=str, sort_keys=True)[:16000])
        except Exception:
            pass
        return Response(status=204)
