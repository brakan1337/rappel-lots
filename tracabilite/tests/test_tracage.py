from decimal import Decimal

from tracabilite.models import Composition, Rappel
from tracabilite.tracage import arbre, clore_rappel, lancer_rappel, lots_en_amont, lots_en_aval, mesurer_impact


def _numeros(traces):
    return {(t.lot.numero, t.profondeur) for t in traces}


def test_l_aval_suit_la_chaine_sur_plusieurs_niveaux(usine):
    assert _numeros(lots_en_aval(usine["poulet"])) == {
        ("PI-FON", 1),
        ("PF-BAS", 1),
        ("PF-BOU", 2),
        ("PF-VEL", 2),
    }


def test_l_amont_remonte_jusqu_aux_matieres(usine):
    assert _numeros(lots_en_amont(usine["bourguignon"])) == {("PI-FON", 1), ("MP-POU", 2)}


def test_un_lot_sans_lien_n_a_ni_amont_ni_aval(usine):
    assert lots_en_aval(usine["gratin"]) == []
    assert lots_en_amont(usine["poulet"]) == []


def test_une_boucle_dans_les_donnees_ne_bloque_pas_la_requete(usine):
    # Donnée erronée : le bourguignon serait entré dans le fond. La requête doit quand même s'arrêter.
    Composition.objects.create(lot_utilise=usine["bourguignon"], lot_produit=usine["fond"], quantite=Decimal(1))
    numeros = {t.lot.numero for t in lots_en_aval(usine["poulet"])}
    assert numeros == {"PI-FON", "PF-BAS", "PF-BOU", "PF-VEL"}


def test_l_arbre_garde_les_quantites_et_les_unites(usine):
    racine = arbre(usine["bourguignon"], vers_l_aval=False)
    fond = racine.enfants[0]
    assert (fond.lot.numero, fond.quantite, fond.unite) == ("PI-FON", Decimal(6), "kg")
    assert [n.lot.numero for n in fond.enfants] == ["MP-POU"]


def test_l_impact_compte_les_clients_et_les_quantites(usine):
    impact = mesurer_impact(usine["poulet"])
    assert {l.numero for l in impact.lots_finis} == {"PF-BAS", "PF-BOU", "PF-VEL"}
    assert [c.nom for c in impact.clients] == ["Cantine A", "Épicerie B"]
    # Le gratin livré à l'Épicerie B ne contient pas de poulet : il n'apparaît pas.
    epicerie = impact.clients[1]
    assert [l.lot.numero for l in epicerie.lignes] == ["PF-VEL"]
    assert impact.quantite_produite == Decimal(470)  # 200 + 150 + 120
    assert impact.quantite_expediee == Decimal(120)  # 50 + 30 + 40
    assert impact.quantite_en_stock == Decimal(350)


def test_lancer_un_rappel_bloque_le_lot_et_tout_l_aval(usine, qualite):
    rappel = lancer_rappel(usine["poulet"], motif="Listeria", niveau=Rappel.Niveau.RAPPEL, par=qualite)
    assert rappel.numero.startswith("RAP-") and rappel.numero.endswith("-001")
    assert {l.numero for l in rappel.lots_bloques.all()} == {"MP-POU", "PI-FON", "PF-BAS", "PF-BOU", "PF-VEL"}
    assert usine["veloute"].est_bloque
    assert not usine["gratin"].est_bloque


def test_les_numeros_de_rappel_se_suivent(usine):
    premier = lancer_rappel(usine["poulet"], motif="a", niveau=Rappel.Niveau.RETRAIT)
    second = lancer_rappel(usine["carottes"], motif="b", niveau=Rappel.Niveau.RETRAIT)
    assert premier.numero[-3:] == "001" and second.numero[-3:] == "002"


def test_clore_un_rappel_debloque_ses_lots(usine):
    rappel = lancer_rappel(usine["poulet"], motif="Listeria", niveau=Rappel.Niveau.RETRAIT)
    clore_rappel(rappel)
    assert not usine["veloute"].est_bloque
    assert rappel.clos_le is not None


def test_un_lot_reste_bloque_tant_qu_un_autre_rappel_est_ouvert(usine):
    premier = lancer_rappel(usine["poulet"], motif="a", niveau=Rappel.Niveau.RETRAIT)
    lancer_rappel(usine["fond"], motif="b", niveau=Rappel.Niveau.RETRAIT)
    clore_rappel(premier)
    assert usine["veloute"].est_bloque
