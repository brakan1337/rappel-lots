"""
Une petite usine de test, assez simple pour vérifier chaque résultat à la main :

    poulet ──► fond de volaille ──► bourguignon ──► livré à Cantine A
         │                    └──► velouté      ──► livré à Cantine A et Épicerie B
         └──► poulet basquaise (pas encore livré)
    tomates ──► poulet basquaise
    carottes ──► gratin (sans lien avec le poulet) ──► livré à Épicerie B
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from tracabilite.models import Article, Client, Composition, Expedition, Fournisseur, LigneExpedition, Lot

J = date(2026, 11, 2)


def _lot(numero, article, jour=J, fournisseur=None, quantite=100):
    return Lot.objects.create(
        numero=numero,
        article=article,
        fournisseur=fournisseur,
        numero_fournisseur="F-" + numero if fournisseur else "",
        date=jour,
        dlc=date(2026, 11, 20),
        quantite=Decimal(quantite),
    )


def _lier(utilise, produit, quantite=5):
    Composition.objects.create(lot_utilise=utilise, lot_produit=produit, quantite=Decimal(quantite))


@pytest.fixture
def usine(db):
    volailles = Fournisseur.objects.create(nom="Volailles test", ville="Hagetmau")
    primeurs = Fournisseur.objects.create(nom="Primeurs test", ville="Dax")
    art = {
        code: Article.objects.create(code=code, libelle=libelle, nature=nature, unite=unite)
        for code, libelle, nature, unite in [
            ("POU", "Poulet", "MATIERE", "KG"),
            ("TOM", "Tomates", "MATIERE", "KG"),
            ("CAR", "Carottes", "MATIERE", "KG"),
            ("FON", "Fond de volaille", "INTERMEDIAIRE", "KG"),
            ("BOU", "Bourguignon", "FINI", "UNITE"),
            ("VEL", "Velouté", "FINI", "UNITE"),
            ("BAS", "Poulet basquaise", "FINI", "UNITE"),
            ("GRA", "Gratin", "FINI", "UNITE"),
        ]
    }
    lots = {
        "poulet": _lot("MP-POU", art["POU"], date(2026, 11, 1), volailles),
        "tomates": _lot("MP-TOM", art["TOM"], date(2026, 11, 1), primeurs),
        "carottes": _lot("MP-CAR", art["CAR"], date(2026, 11, 1), primeurs),
        "fond": _lot("PI-FON", art["FON"]),
        "bourguignon": _lot("PF-BOU", art["BOU"], quantite=200),
        "veloute": _lot("PF-VEL", art["VEL"], quantite=150),
        "basquaise": _lot("PF-BAS", art["BAS"], quantite=120),
        "gratin": _lot("PF-GRA", art["GRA"], quantite=300),
    }
    _lier(lots["poulet"], lots["fond"], 12)
    _lier(lots["fond"], lots["bourguignon"], 6)
    _lier(lots["fond"], lots["veloute"], 8)
    _lier(lots["poulet"], lots["basquaise"], 14)
    _lier(lots["tomates"], lots["basquaise"], 9)
    _lier(lots["carottes"], lots["gratin"], 4)

    cantine = Client.objects.create(nom="Cantine A", ville="Soustons")
    epicerie = Client.objects.create(nom="Épicerie B", ville="Dax")
    e1 = Expedition.objects.create(numero="BL-1", client=cantine, date=date(2026, 11, 3))
    e2 = Expedition.objects.create(numero="BL-2", client=epicerie, date=date(2026, 11, 4))
    LigneExpedition.objects.create(expedition=e1, lot=lots["bourguignon"], quantite=Decimal(50))
    LigneExpedition.objects.create(expedition=e1, lot=lots["veloute"], quantite=Decimal(30))
    LigneExpedition.objects.create(expedition=e2, lot=lots["veloute"], quantite=Decimal(40))
    LigneExpedition.objects.create(expedition=e2, lot=lots["gratin"], quantite=Decimal(60))
    return lots


@pytest.fixture
def qualite(db):
    utilisateur = User.objects.create_user("qualite-test", password="mot-de-passe-test", is_staff=True)
    utilisateur.user_permissions.set(Permission.objects.filter(content_type__app_label="tracabilite"))
    return utilisateur


@pytest.fixture
def api(db):
    entrepot = User.objects.create_user("entrepot-test")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=entrepot).key}")
    return client
