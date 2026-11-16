from rest_framework.test import APIClient

from tracabilite.models import Expedition, Rappel
from tracabilite.tracage import lancer_rappel

NOUVELLE_EXPEDITION = {
    "numero": "BL-NOUVEAU",
    "client": "Cantine A",
    "date": "2026-11-05",
    "lignes": [{"lot": "PF-BAS", "quantite": "40"}],
}


def test_l_api_exige_une_authentification(usine):
    assert APIClient().get("/api/lots/PF-BAS/").status_code == 401


def test_la_fiche_d_un_lot(usine, api):
    reponse = api.get("/api/lots/PF-BAS/")
    assert reponse.status_code == 200
    assert reponse.json()["article"]["libelle"] == "Poulet basquaise"
    assert reponse.json()["est_bloque"] is False


def test_un_lot_inconnu_renvoie_404(usine, api):
    assert api.get("/api/lots/INCONNU/").status_code == 404


def test_aval_et_amont(usine, api):
    aval = api.get("/api/lots/MP-POU/aval/").json()
    assert {(l["numero"], l["profondeur"]) for l in aval} == {
        ("PI-FON", 1),
        ("PF-BAS", 1),
        ("PF-BOU", 2),
        ("PF-VEL", 2),
    }
    amont = api.get("/api/lots/PF-VEL/amont/").json()
    assert [l["numero"] for l in amont] == ["PI-FON", "MP-POU"]


def test_l_entrepot_expedie_un_lot_libre(usine, api):
    reponse = api.post("/api/expeditions/", NOUVELLE_EXPEDITION, format="json")
    assert reponse.status_code == 201, reponse.json()
    assert reponse.json()["lignes"] == [{"lot": "PF-BAS", "quantite": "40.00"}]
    assert Expedition.objects.filter(numero="BL-NOUVEAU").exists()


def test_l_entrepot_ne_peut_pas_expedier_un_lot_bloque(usine, api):
    rappel = lancer_rappel(usine["poulet"], motif="Listeria", niveau=Rappel.Niveau.RAPPEL)
    reponse = api.post("/api/expeditions/", NOUVELLE_EXPEDITION, format="json")
    assert reponse.status_code == 400
    assert "bloqué" in str(reponse.json()["lignes"])
    assert not Expedition.objects.filter(numero="BL-NOUVEAU").exists()
    assert api.get("/api/lots/PF-BAS/").json()["rappels_ouverts"] == [rappel.numero]


def test_une_expedition_vide_est_refusee(usine, api):
    reponse = api.post("/api/expeditions/", {**NOUVELLE_EXPEDITION, "lignes": []}, format="json")
    assert reponse.status_code == 400


def test_la_liste_des_lots_bloques(usine, api):
    assert api.get("/api/lots/bloques/").json() == []
    lancer_rappel(usine["fond"], motif="x", niveau=Rappel.Niveau.RETRAIT)
    assert api.get("/api/lots/bloques/").json() == ["PF-BOU", "PF-VEL", "PI-FON"]


def test_le_detail_d_un_rappel_liste_les_clients(usine, api):
    rappel = lancer_rappel(usine["poulet"], motif="Listeria", niveau=Rappel.Niveau.RAPPEL)
    donnees = api.get(f"/api/rappels/{rappel.numero}/").json()
    assert [c["nom"] for c in donnees["clients_a_prevenir"]] == ["Cantine A", "Épicerie B"]
    assert api.get("/api/rappels/?statut=ouvert").json()[0]["numero"] == rappel.numero
