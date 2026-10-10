"""
Lance l'application du Dynasty Night Club sur le réseau local pour que le personnel connecté au même réseau
puisse l'utiliser depuis leur navigateur.

Utilisation :  python lancer_reseau.py          (port 8000)
               python lancer_reseau.py 8080     (autre port)

Le serveur s'arrête avec Ctrl+C. Le pare-feu Windows doit autoriser le port choisi.
"""
import os
import socket
import sys


def adresse_ip_locale():
    """Adresse IP de ce PC sur le réseau local (aucune donnée n'est envoyée)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(('10.255.255.255', 1))
            return s.getsockname()[0]
        except OSError:
            return '127.0.0.1'


def main():
    sys.stdout.reconfigure(line_buffering=True)  # afficher le lien immédiatement
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    ip = adresse_ip_locale()
    nom_pc = socket.gethostname()

    # Ces valeurs priment sur celles du fichier .env (load_dotenv ne les écrase pas)
    os.environ['DEBUG'] = 'False'
    os.environ['ALLOWED_HOSTS'] = ','.join(['localhost', '127.0.0.1', ip, nom_pc, nom_pc.lower()])
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dynasty.settings')

    import django
    from django.core.management import call_command

    django.setup()
    call_command('migrate', interactive=False, verbosity=0)
    call_command('collectstatic', interactive=False, verbosity=0)

    from waitress import serve
    from dynasty.wsgi import application

    print()
    print('  Dynasty Night Club est accessible sur le réseau local')
    print('  ------------------------------------------------')
    print(f'  Lien à partager : http://{ip}:{port}')
    print(f'  Sur ce PC       : http://localhost:{port}')
    print()
    print('  Les téléphones et tablettes doivent être connectés au même réseau (Wi-Fi ou partage de connexion).')
    print('  Arrêt du serveur : Ctrl+C')
    print()
    serve(application, listen=f'0.0.0.0:{port}', threads=8)


if __name__ == '__main__':
    main()
