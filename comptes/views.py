from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def accueil(request):
    """Le gérant arrive sur le tableau de bord, le personnel sur la caisse."""
    return redirect('tableau_de_bord' if request.user.is_superuser else 'tables')
