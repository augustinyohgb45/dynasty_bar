from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Dynasty Night Club · administration"
admin.site.site_title = "Dynasty Night Club"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('compte/', include('comptes.urls')),
    path('', include('stock.urls')),
]
