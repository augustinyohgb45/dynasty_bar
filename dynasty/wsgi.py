import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dynasty.settings')

try:
    application = get_wsgi_application()
except Exception as erreur:
    if not os.environ.get('VERCEL'):
        raise
    # En ligne, une configuration incomplète (variable manquante…) s'affiche clairement au lieu
    # d'une erreur 500 muette ; seul le type et le message sont montrés, jamais de valeur secrète.
    message = f"Configuration incomplète : {type(erreur).__name__} : {erreur}".encode('utf-8')

    def application(environ, start_response):
        start_response('503 Service Unavailable', [('Content-Type', 'text/plain; charset=utf-8')])
        return [message]

# Point d'entrée attendu par Vercel
app = application
