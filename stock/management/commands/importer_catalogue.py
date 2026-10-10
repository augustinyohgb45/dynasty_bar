from django.core.management.base import BaseCommand, CommandError

from stock.importation import ErreurImport, importer_catalogue


class Command(BaseCommand):
    help = "Importe (ou met à jour) le catalogue du bar depuis le classeur Excel de gestion de stock."

    def add_arguments(self, parser):
        parser.add_argument('fichier', help="Chemin du classeur (.xlsx ou .xlsm)")
        parser.add_argument('--simulation', action='store_true',
                            help="Affiche ce qui serait importé sans rien enregistrer.")

    def handle(self, fichier, simulation, **options):
        try:
            rapport = importer_catalogue(fichier, simulation=simulation)
        except (ErreurImport, FileNotFoundError) as e:
            raise CommandError(str(e))

        if simulation:
            self.stdout.write(self.style.WARNING("Simulation : rien n'a été enregistré."))
        self.stdout.write(self.style.SUCCESS(
            f"{rapport.nb_produits} produits importés ({len(rapport.crees)} créés, "
            f"{len(rapport.mis_a_jour)} mis à jour)."))
        for produit, quantite in rapport.stocks_initiaux:
            self.stdout.write(f"  Stock initial : {produit} = {quantite}")
        for avertissement in rapport.avertissements:
            self.stdout.write(self.style.WARNING(f"  ! {avertissement}"))
        self.stdout.write(f"  {len(rapport.sans_prix_achat)} produits sans prix d'achat, "
                          f"{len(rapport.sans_seuil)} sans seuil d'alerte.")
