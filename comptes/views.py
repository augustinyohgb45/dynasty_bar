from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import gerant_requis
from .forms import CompteForm, ModifierCompteForm, MotDePasseForm


@login_required
def accueil(request):
    """L'admin arrive sur le tableau de bord, la caisse sur le plan des tables."""
    return redirect('tableau_de_bord' if request.user.is_superuser else 'tables')


@gerant_requis
def personnel(request):
    comptes = User.objects.order_by('-is_active', '-is_superuser', 'username')
    return render(request, 'comptes/personnel.html', {'comptes': comptes})


@gerant_requis
def compte_nouveau(request):
    form = CompteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        compte = form.save()
        role = "admin" if compte.is_superuser else "caisse"
        messages.success(request, f"Compte « {compte.username} » ({role}) créé. Communiquez-lui son mot de passe "
                                  "de façon discrète.")
        return redirect('personnel')
    return render(request, 'comptes/compte_form.html', {'form': form, 'creation': True})


@gerant_requis
def compte_modifier(request, compte_id):
    compte = get_object_or_404(User, pk=compte_id)
    form = ModifierCompteForm(request.POST if 'enregistrer' in request.POST else None,
                              instance=compte, demandeur=request.user)
    form_mdp = MotDePasseForm(compte, request.POST if 'mot_de_passe' in request.POST else None)
    if 'enregistrer' in request.POST and form.is_valid():
        form.save()
        messages.success(request, f"Compte « {compte.username} » mis à jour.")
        return redirect('personnel')
    if 'mot_de_passe' in request.POST and form_mdp.is_valid():
        form_mdp.save()
        messages.success(request, f"Nouveau mot de passe enregistré pour « {compte.username} ».")
        return redirect('personnel')
    return render(request, 'comptes/compte_form.html', {'form': form, 'form_mdp': form_mdp, 'compte': compte})
