from django.contrib.auth import views as auth_views
from django.urls import path

urlpatterns = [
    path('connexion/', auth_views.LoginView.as_view(template_name='comptes/connexion.html',
                                                    redirect_authenticated_user=True), name='connexion'),
    path('deconnexion/', auth_views.LogoutView.as_view(next_page='connexion'), name='deconnexion'),
]
