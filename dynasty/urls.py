from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

admin.site.site_header = "Dynasty Night Club · administration"
admin.site.site_title = "Dynasty Night Club"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('compte/', include('comptes.urls')),
    path('caisse/', include('caisse.urls')),
    path('stock/', include('stock.urls')),
    path('', RedirectView.as_view(pattern_name='tables', permanent=False)),
]
