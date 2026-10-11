from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('connexion/', auth_views.LoginView.as_view(template_name='comptes/connexion.html',
                                                    redirect_authenticated_user=True), name='connexion'),
    path('deconnexion/', auth_views.LogoutView.as_view(next_page='connexion'), name='deconnexion'),
    # Comptes du personnel (admin)
    path('personnel/', views.personnel, name='personnel'),
    path('personnel/nouveau/', views.compte_nouveau, name='compte_nouveau'),
    path('personnel/<int:compte_id>/', views.compte_modifier, name='compte_modifier'),
]
