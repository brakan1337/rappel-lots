"""
Génère un mois d'activité d'une cuisine centrale fictive : réceptions de matières,
fabrication de sauces et de fonds, puis de plats, et expéditions aux clients.

Tout est fictif. Le tirage est déterministe (graine fixe) : deux chargements donnent
exactement les mêmes données, ce qui rend la démonstration reproductible.

    python manage.py charger_demo --reset
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.authtoken.models import Token

from tracabilite.models import (
    Article,
    Client,
    Composition,
    Expedition,
    Fournisseur,
    LigneExpedition,
    Lot,
    Rappel,
)

DEBUT = date(2026, 10, 12)
FIN = date(2026, 11, 14)

# Le lot que le fournisseur de volailles signalera : le scénario de la démonstration.
LOT_SIGNALE = ("POU", date(2026, 10, 27), "V-2210")

FOURNISSEURS = {
    "Primeurs Darrigade": ("Mont-de-Marsan", "P"),
    "Volailles Bénesse": ("Hagetmau", "V"),
    "Viandes Larrieu": ("Dax", "L"),
    "Laiterie Hourcade": ("Pau", "H"),
    "Minoterie Peyrot": ("Aire-sur-l'Adour", "M"),
    "Épicerie Corbin": ("Bayonne", "C"),
}

# code : (libellé, fournisseur, jours entre deux réceptions, durée de conservation, unité)
MATIERES = {
    "TOM": ("Tomates", "Primeurs Darrigade", 3, 8, "KG"),
    "OIG": ("Oignons", "Primeurs Darrigade", 5, 30, "KG"),
    "CAR": ("Carottes", "Primeurs Darrigade", 4, 15, "KG"),
    "PDT": ("Pommes de terre", "Primeurs Darrigade", 5, 30, "KG"),
    "CHA": ("Champignons de Paris", "Primeurs Darrigade", 3, 6, "KG"),
    "POU": ("Filets de poulet", "Volailles Bénesse", 3, 6, "KG"),
    "OEU": ("Œufs frais", "Volailles Bénesse", 4, 25, "UNITE"),
    "BOE": ("Bœuf à braiser", "Viandes Larrieu", 3, 7, "KG"),
    "CRE": ("Crème fraîche", "Laiterie Hourcade", 4, 15, "KG"),
    "LAI": ("Lait entier", "Laiterie Hourcade", 4, 10, "KG"),
    "BEU": ("Beurre doux", "Laiterie Hourcade", 7, 45, "KG"),
    "FAR": ("Farine de blé", "Minoterie Peyrot", 10, 180, "KG"),
    "RIZ": ("Riz long", "Minoterie Peyrot", 10, 365, "KG"),
    "HUI": ("Huile d'olive", "Épicerie Corbin", 14, 365, "KG"),
    "EPI": ("Herbes et épices", "Épicerie Corbin", 14, 365, "KG"),
}

# code : (libellé, jours entre deux fabrications, recette pour un lot en kg ou unités, quantité produite)
INTERMEDIAIRES = {
    "SAU": ("Sauce tomate maison", 2, {"TOM": 40, "OIG": 8, "HUI": 2, "EPI": 0.5}, 45),
    "FON": ("Fond de volaille", 3, {"POU": 12, "CAR": 6, "OIG": 5, "EPI": 0.3}, 40),
    "BEC": ("Sauce béchamel", 2, {"LAI": 30, "BEU": 3, "FAR": 3}, 34),
    "PAT": ("Pâte brisée", 3, {"FAR": 12, "BEU": 6, "OEU": 30}, 20),
}

# code : (libellé, recette pour 100 portions)
PLATS = {
    "BAS": ("Poulet basquaise", {"POU": 14, "SAU": 9, "RIZ": 8}),
    "BOU": ("Bœuf bourguignon", {"BOE": 16, "CAR": 4, "CHA": 3, "FON": 6}),
    "GRA": ("Gratin dauphinois", {"PDT": 22, "CRE": 5, "LAI": 4}),
    "LAS": ("Lasagnes à la bolognaise", {"BOE": 10, "SAU": 8, "BEC": 7, "FAR": 3}),
    "PAR": ("Hachis parmentier", {"BOE": 11, "PDT": 15, "BEU": 1, "LAI": 3}),
    "RIZ": ("Riz au poulet et champignons", {"POU": 11, "RIZ": 9, "CRE": 3, "CHA": 4, "FON": 4}),
    "QUI": ("Quiche aux légumes", {"PAT": 8, "OEU": 60, "CRE": 4, "CAR": 3, "OIG": 2}),
    "VEL": ("Velouté de champignons", {"CHA": 9, "CRE": 4, "FON": 8, "OIG": 2}),
}

CLIENTS = [
    ("Supérette de Saint-Sever", "Saint-Sever"),
    ("Cantine scolaire de Grenade-sur-l'Adour", "Grenade-sur-l'Adour"),
    ("Restaurant d'entreprise de Tarnos", "Tarnos"),
    ("Épicerie fine de Dax", "Dax"),
    ("Traiteur de Biarritz", "Biarritz"),
    ("Résidence seniors de Morcenx", "Morcenx"),
    ("Supérette de Mimizan", "Mimizan"),
    ("Cafétéria de l'hôpital de Mont-de-Marsan", "Mont-de-Marsan"),
    ("Cantine scolaire de Soustons", "Soustons"),
    ("Épicerie du marché d'Orthez", "Orthez"),
    ("Restaurant d'entreprise de Lacq", "Lacq"),
    ("Supérette de Capbreton", "Capbreton"),
]


def jours(debut: date, fin: date):
    jour = debut
    while jour <= fin:
        yield jour
        jour += timedelta(days=1)


class Command(BaseCommand):
    help = "Charge un mois de données fictives de traçabilité, et les comptes de démonstration."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Efface d'abord toutes les données métier.")
        parser.add_argument("--mot-de-passe", default="demo-qualite", help="Mot de passe du compte « qualite ».")

    @transaction.atomic
    def handle(self, *args, reset, mot_de_passe, **options):
        if Lot.objects.exists():
            if not reset:
                raise CommandError("Des données existent déjà. Relancez avec --reset pour les remplacer.")
            for modele in (Rappel, LigneExpedition, Expedition, Composition, Lot, Article, Client, Fournisseur):
                modele.objects.all().delete()

        self.hasard = random.Random(42)
        self.fournisseurs = {
            nom: Fournisseur.objects.create(
                nom=nom, ville=ville, email=f"qualite@{prefixe.lower()}-fournisseur.example"
            )
            for nom, (ville, prefixe) in FOURNISSEURS.items()
        }
        self.articles = self._creer_articles()
        self.clients = [
            Client.objects.create(nom=nom, ville=ville, adresse="Zone d'activité", email=f"achats{i}@client.example")
            for i, (nom, ville) in enumerate(CLIENTS, start=1)
        ]
        self.derniers: dict[str, list[Lot]] = {}  # code article → lots disponibles, le plus récent en dernier
        self.reste: dict[int, Decimal] = {}  # lot de plat → portions encore à l'usine
        self.compteur_fournisseur = 1000

        plats = list(PLATS)
        for jour in jours(DEBUT, FIN):
            self._receptions(jour)
            if jour.weekday() == 6:
                continue  # pas de fabrication ni de livraison le dimanche
            self._intermediaires(jour)
            for code in self.hasard.sample(plats, k=self.hasard.randint(3, 4)):
                self._plat(code, jour)
            self._expeditions(jour)

        self._comptes(mot_de_passe)
        signale = Lot.objects.get(numero_fournisseur=LOT_SIGNALE[2])
        self.stdout.write(
            self.style.SUCCESS(
                f"{Lot.objects.count()} lots, {Composition.objects.count()} liens de composition, "
                f"{Expedition.objects.count()} expéditions."
            )
        )
        self.stdout.write(f"Scénario : le fournisseur signale le lot {signale.numero_fournisseur} ({signale.numero}).")

    def _creer_articles(self):
        articles = {}
        for code, (libelle, *_, unite) in MATIERES.items():
            articles[code] = Article.objects.create(code=f"MP-{code}", libelle=libelle, nature="MATIERE", unite=unite)
        for code, (libelle, *_) in INTERMEDIAIRES.items():
            articles[code] = Article.objects.create(code=f"PI-{code}", libelle=libelle, nature="INTERMEDIAIRE")
        for code, (libelle, _) in PLATS.items():
            articles[f"PF-{code}"] = Article.objects.create(
                code=f"PF-{code}", libelle=libelle, nature="FINI", unite="UNITE"
            )
        return articles

    def _numero(self, prefixe: str, jour: date, code: str) -> str:
        base = f"{prefixe}-{jour:%Y%m%d}-{code}"
        numero, rang = base, 2
        while Lot.objects.filter(numero=numero).exists():
            numero, rang = f"{base}-{rang}", rang + 1
        return numero

    def _receptions(self, jour: date):
        decalage = (jour - DEBUT).days
        for i, (code, (_, fournisseur, frequence, conservation, unite)) in enumerate(MATIERES.items()):
            # Chaque matière a son propre rythme, décalé pour que tout n'arrive pas le même jour.
            if (decalage + i) % frequence and not (code, jour) == LOT_SIGNALE[:2]:
                continue
            self.compteur_fournisseur += self.hasard.randint(3, 40)
            prefixe = FOURNISSEURS[fournisseur][1]
            numero_fournisseur = (
                LOT_SIGNALE[2] if (code, jour) == LOT_SIGNALE[:2] else f"{prefixe}-{self.compteur_fournisseur}"
            )
            lot = Lot.objects.create(
                numero=self._numero("MP", jour, code),
                article=self.articles[code],
                fournisseur=self.fournisseurs[fournisseur],
                numero_fournisseur=numero_fournisseur,
                date=jour,
                dlc=jour + timedelta(days=conservation),
                quantite=Decimal(self.hasard.randint(80, 400)) * (10 if unite == "UNITE" else 1),
            )
            self.derniers.setdefault(code, []).append(lot)

    def _utiliser(self, lot: Lot, recette: dict, facteur: float, jour: date):
        for code, quantite in recette.items():
            candidats = [l for l in self.derniers.get(code, []) if l.date <= jour]
            if not candidats:
                continue
            # Le plus souvent on finit le lot entamé ; parfois on mélange avec le précédent (fin de lot).
            utilises = candidats[-2:] if len(candidats) > 1 and self.hasard.random() < 0.3 else candidats[-1:]
            part = Decimal(str(round(quantite * facteur / len(utilises), 2)))
            for entrant in utilises:
                Composition.objects.create(lot_produit=lot, lot_utilise=entrant, quantite=part)

    def _intermediaires(self, jour: date):
        decalage = (jour - DEBUT).days
        for code, (_, frequence, recette, produit) in INTERMEDIAIRES.items():
            if decalage % frequence:
                continue
            lot = Lot.objects.create(
                numero=self._numero("PI", jour, code),
                article=self.articles[code],
                date=jour,
                dlc=jour + timedelta(days=4),
                quantite=Decimal(produit),
            )
            self._utiliser(lot, recette, 1, jour)
            self.derniers.setdefault(code, []).append(lot)

    def _plat(self, code: str, jour: date):
        portions = self.hasard.randrange(150, 400, 10)
        lot = Lot.objects.create(
            numero=self._numero("PF", jour, code),
            article=self.articles[f"PF-{code}"],
            date=jour,
            dlc=jour + timedelta(days=7),
            quantite=Decimal(portions),
        )
        self._utiliser(lot, PLATS[code][1], portions / 100, jour)
        self.reste[lot.pk] = Decimal(portions)
        self.derniers.setdefault(f"PF-{code}", []).append(lot)

    def _expeditions(self, jour: date):
        frais = [
            l
            for lots in (v for k, v in self.derniers.items() if k.startswith("PF-"))
            for l in lots
            if 0 <= (jour - l.date).days <= 3 and self.reste[l.pk] >= 20
        ]
        for rang in range(1, self.hasard.randint(4, 7) + 1):
            if not frais:
                return
            expedition = Expedition.objects.create(
                numero=f"BL-{jour:%Y%m%d}-{rang:02d}", client=self.hasard.choice(self.clients), date=jour
            )
            for lot in self.hasard.sample(frais, k=min(len(frais), self.hasard.randint(1, 4))):
                quantite = min(self.reste[lot.pk], Decimal(self.hasard.randrange(20, 90, 10)))
                LigneExpedition.objects.create(expedition=expedition, lot=lot, quantite=quantite)
                self.reste[lot.pk] -= quantite
            frais = [l for l in frais if self.reste[l.pk] >= 20]

    def _comptes(self, mot_de_passe: str):
        qualite, _ = User.objects.get_or_create(username="qualite", defaults={"first_name": "Service qualité"})
        qualite.is_staff = True
        qualite.set_password(mot_de_passe)
        qualite.save()
        qualite.user_permissions.set(Permission.objects.filter(content_type__app_label="tracabilite"))

        entrepot, _ = User.objects.get_or_create(username="entrepot", defaults={"first_name": "Entrepôt"})
        entrepot.set_unusable_password()
        entrepot.save()
        Token.objects.filter(user=entrepot).delete()
        jeton = Token.objects.create(user=entrepot)
        self.stdout.write(f"Compte « qualite » prêt. Jeton d'API de l'entrepôt : {jeton.key}")
