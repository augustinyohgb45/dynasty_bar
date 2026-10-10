from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def gerant_requis(vue):
    """Réserve la vue au gérant (compte administrateur) ; 403 pour le personnel."""
    @login_required
    @wraps(vue)
    def vue_protegee(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return vue(request, *args, **kwargs)
    return vue_protegee
