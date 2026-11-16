from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from tracabilite.models import Composition, Expedition, LigneExpedition, Lot, Rappel
from tracabilite.tracage import lancer_rappel


def test_une_matiere_premiere_exige_un_fournisseur(usine):
    lot = Lot(numero="MP-X", article=usine["poulet"].article, date=date(2026, 11, 1), dlc=date(2026, 11, 5), quantite=1)
    with pytest.raises(ValidationError, match="fournisseur"):
        lot.full_clean()


def test_la_dlc_ne_precede_pas_la_date(usine):
    lot = usine["fond"]
    lot.dlc = date(2026, 10, 1)
    with pytest.raises(ValidationError, match="DLC"):
        lot.full_clean()


def test_un_lot_ne_peut_pas_servir_avant_d_exister(usine):
    tardif = Lot.objects.create(
        numero="MP-TARDIF",
        article=usine["poulet"].article,
        fournisseur=usine["poulet"].fournisseur,
        date=date(2026, 11, 10),
        dlc=date(2026, 11, 15),
        quantite=Decimal(10),
    )
    composition = Composition(lot_utilise=tardif, lot_produit=usine["fond"], quantite=Decimal(1))
    with pytest.raises(ValidationError, match="avant"):
        composition.full_clean()


def test_une_matiere_premiere_ne_se_fabrique_pas(usine):
    composition = Composition(lot_utilise=usine["tomates"], lot_produit=usine["poulet"], quantite=Decimal(1))
    with pytest.raises(ValidationError, match="reçoit"):
        composition.full_clean()


def test_la_base_refuse_un_lot_compose_de_lui_meme(usine):
    with pytest.raises(IntegrityError):
        Composition.objects.create(lot_utilise=usine["fond"], lot_produit=usine["fond"], quantite=Decimal(1))


def test_on_ne_peut_pas_expedier_un_lot_bloque(usine):
    lancer_rappel(usine["poulet"], motif="Listeria", niveau=Rappel.Niveau.RETRAIT)
    ligne = LigneExpedition(expedition=Expedition.objects.first(), lot=usine["basquaise"], quantite=Decimal(10))
    with pytest.raises(ValidationError, match="bloqué"):
        ligne.full_clean()


def test_on_n_expedie_que_des_produits_finis(usine):
    ligne = LigneExpedition(expedition=Expedition.objects.first(), lot=usine["fond"], quantite=Decimal(10))
    with pytest.raises(ValidationError, match="produits finis"):
        ligne.full_clean()


def test_le_filtre_des_lots_bloques(usine):
    lancer_rappel(usine["fond"], motif="x", niveau=Rappel.Niveau.RETRAIT)
    assert set(Lot.objects.bloques().values_list("numero", flat=True)) == {"PI-FON", "PF-BOU", "PF-VEL"}
