import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from tracabilite.models import Lot, Rappel
from tracabilite.tracage import lancer_rappel


def test_les_pages_exigent_une_connexion(usine, client):
    reponse = client.get("/lots/PF-BAS/")
    assert reponse.status_code == 302
    assert "/admin/login/" in reponse["Location"]


def test_la_recherche_par_numero_fournisseur_ouvre_la_fiche(usine, client, qualite):
    client.force_login(qualite)
    reponse = client.get("/", {"q": "F-MP-POU"})
    assert reponse.status_code == 302
    assert reponse["Location"] == "/lots/MP-POU/"


def test_la_fiche_montre_l_impact(usine, client, qualite):
    client.force_login(qualite)
    page = client.get("/lots/MP-POU/").content.decode()
    assert "Cantine A" in page and "Épicerie B" in page
    assert "Lancer le rappel" in page


def test_lancer_un_rappel_depuis_la_fiche(usine, client, qualite):
    client.force_login(qualite)
    reponse = client.post("/lots/MP-POU/", {"motif": "Listeria signalée", "niveau": "RAPPEL"})
    rappel = Rappel.objects.get()
    assert reponse["Location"] == f"/rappels/{rappel.numero}/"
    assert rappel.cree_par == qualite
    assert rappel.lots_bloques.count() == 5


def test_sans_permission_on_ne_lance_pas_de_rappel(usine, client):
    simple = User.objects.create_user("visiteur", password="mot-de-passe-test")
    client.force_login(simple)
    page = client.get("/lots/MP-POU/").content.decode()
    assert "Lancer le rappel" not in page
    assert client.post("/lots/MP-POU/", {"motif": "x", "niveau": "RETRAIT"}).status_code == 403
    assert not Rappel.objects.exists()


def test_les_courriers_s_adressent_a_chaque_client(usine, client, qualite):
    rappel = lancer_rappel(usine["poulet"], motif="Listeria", niveau=Rappel.Niveau.RAPPEL)
    client.force_login(qualite)
    page = client.get(f"/rappels/{rappel.numero}/courriers/").content.decode()
    assert page.count('class="courrier"') == 2
    assert "afficher en magasin" in page  # niveau « rappel » : les consommateurs sont prévenus


def test_clore_depuis_la_page_du_rappel(usine, client, qualite):
    rappel = lancer_rappel(usine["poulet"], motif="Listeria", niveau=Rappel.Niveau.RETRAIT)
    client.force_login(qualite)
    client.post(f"/rappels/{rappel.numero}/clore/")
    rappel.refresh_from_db()
    assert rappel.statut == Rappel.Statut.CLOS


def test_le_back_office_s_ouvre(usine, client, qualite):
    client.force_login(qualite)
    assert client.get("/admin/tracabilite/lot/").status_code == 200
    assert client.get("/admin/tracabilite/lot/?bloque=oui").status_code == 200


@pytest.mark.django_db
def test_les_donnees_de_demo_contiennent_le_scenario(capsys):
    call_command("charger_demo")
    lot = Lot.objects.get(numero_fournisseur="V-2210")
    from tracabilite.tracage import mesurer_impact

    impact = mesurer_impact(lot)
    assert max(t.profondeur for t in impact.aval) == 2
    assert len(impact.clients) >= 5
    assert "V-2210" in capsys.readouterr().out
