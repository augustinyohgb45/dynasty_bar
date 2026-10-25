"""Configuration de l'application de gestion du Dynasty Night Club."""
import os
import sys
from pathlib import Path

import dj_database_url
from django.contrib.messages import constants as messages
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Secrets et réglages propres à chaque poste dans le fichier .env (voir .env.example)
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ['SECRET_KEY']
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = [h for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'comptes',
    'stock',
    'caisse',
    'audit',
    'gerance',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Sert les fichiers CSS/JS quand DEBUG est désactivé (serveur réseau)
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'audit.journal.AuditMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'dynasty.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'dynasty.wsgi.application'

# En ligne (Vercel + Neon), l'adresse de la base PostgreSQL est fournie par DATABASE_URL ;
# sur le PC du club, sans cette variable, on garde le fichier SQLite local.
URL_BASE = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
if URL_BASE:
    DATABASES = {'default': dj_database_url.parse(URL_BASE, conn_max_age=0, ssl_require=True)}
    # Neon passe par un regroupeur de connexions (pgbouncer) qui ne gère pas les curseurs côté serveur
    DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = True
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Sur le PC : accès à la base en ligne sous le nom « neon » (création des tables, copie des données)
if os.environ.get('NEON_DATABASE_URL'):
    DATABASES['neon'] = dj_database_url.parse(os.environ['NEON_DATABASE_URL'], conn_max_age=0, ssl_require=True)
    DATABASES['neon']['DISABLE_SERVER_SIDE_CURSORS'] = True

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = 'connexion'
LOGIN_REDIRECT_URL = 'accueil'

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = os.environ.get('TIME_ZONE', 'Africa/Abidjan')
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

MESSAGE_TAGS = {
    messages.DEBUG: 'info',
    messages.INFO: 'info',
    messages.SUCCESS: 'succes',
    messages.WARNING: 'attention',
    messages.ERROR: 'erreur',
}

# Une soirée commence à cette heure et se termine à la même heure le lendemain :
# les ventes après minuit restent rattachées à la soirée de la veille.
HEURE_DEBUT_SOIREE = int(os.environ.get('HEURE_DEBUT_SOIREE', 12))

# Hébergement sur Vercel (la variable VERCEL y est toujours définie)
if os.environ.get('VERCEL'):
    ALLOWED_HOSTS += ['.vercel.app'] + [h for h in (os.environ.get('VERCEL_URL'),
                                                    os.environ.get('VERCEL_PROJECT_PRODUCTION_URL')) if h]
    # Formulaires acceptés depuis les adresses Vercel et un éventuel nom de domaine personnel
    CSRF_TRUSTED_ORIGINS = ['https://*.vercel.app'] + [
        o for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o]
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Pas d'étape « collectstatic » sur Vercel : WhiteNoise sert les fichiers depuis leurs dossiers d'origine
    WHITENOISE_USE_FINDERS = True
    STATIC_ROOT = None
    STORAGES['staticfiles'] = {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}

# Tests : hachage rapide des mots de passe (les vrais comptes gardent l'algorithme sûr par défaut)
if 'test' in sys.argv:
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
