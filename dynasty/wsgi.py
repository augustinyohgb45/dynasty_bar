import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dynasty.settings')

application = get_wsgi_application()

# Point d'entrée attendu par Vercel
app = application
