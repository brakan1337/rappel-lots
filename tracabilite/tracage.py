"""
Remonter et descendre la chaîne des lots.

Un lot de poulet entre dans un fond de volaille, qui entre lui-même dans trois plats.
Pour trouver tous les plats touchés, il faut suivre les liens sur plusieurs niveaux.
Une requête récursive (WITH RECURSIVE) le fait en un seul aller-retour avec la base,
quelle que soit la profondeur. Elle fonctionne à l'identique sur PostgreSQL et SQLite.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone

from .models import Article, Composition, LigneExpedition, Lot, Rappel

# Garde-fou : une donnée erronée qui créerait une boucle ne doit pas faire tourner la requête sans fin.
PROFONDEUR_MAX = 20

_REQUETE = """
WITH RECURSIVE chaine(lot_id, profondeur) AS (
    SELECT CAST(%s AS BIGINT), 0
    UNION ALL
    SELECT c.{suivant}, chaine.profondeur + 1
    FROM {table} c
    JOIN chaine ON c.{courant} = chaine.lot_id
    WHERE chaine.profondeur < %s
)
SELECT lot_id, MIN(profondeur)
FROM chaine
WHERE profondeur > 0
GROUP BY lot_id
"""


@dataclass(frozen=True)
class LotTrace:
    lot: Lot
    profondeur: int


def _parcourir(lot: Lot, *, vers_l_aval: bool) -> list[LotTrace]:
    courant, suivant = ("lot_utilise_id", "lot_produit_id") if vers_l_aval else ("lot_produit_id", "lot_utilise_id")
    sql = _REQUETE.format(table=Composition._meta.db_table, courant=courant, suivant=suivant)
    with connection.cursor() as curseur:
        curseur.execute(sql, [lot.pk, PROFONDEUR_MAX])
        profondeurs = dict(curseur.fetchall())
    lots = Lot.objects.filter(pk__in=profondeurs).select_related("article", "fournisseur")
    traces = [LotTrace(l, profondeurs[l.pk]) for l in lots]
    return sorted(traces, key=lambda t: (t.profondeur, t.lot.date, t.lot.numero))


def lots_en_aval(lot: Lot) -> list[LotTrace]:
    """Tous les lots fabriqués, directement ou non, à partir de ce lot."""
    return _parcourir(lot, vers_l_aval=True)


def lots_en_amont(lot: Lot) -> list[LotTrace]:
    """Tous les lots qui sont entrés, directement ou non, dans ce lot."""
    return _parcourir(lot, vers_l_aval=False)


@dataclass
class LivraisonClient:
    """Ce qu'un client a reçu des lots concernés."""

    client_id: int
    nom: str
    ville: str
    adresse: str
    email: str
    lignes: list[LigneExpedition] = field(default_factory=list)

    @property
    def premiere_livraison(self) -> date:
        return min(l.expedition.date for l in self.lignes)


@dataclass
class Impact:
    """Tout ce qu'un rappel sur ce lot toucherait."""

    origine: Lot
    aval: list[LotTrace]
    lots_finis: list[Lot]
    clients: list[LivraisonClient]
    quantite_produite: Decimal
    quantite_expediee: Decimal

    @property
    def lots_a_bloquer(self) -> list[Lot]:
        return [self.origine, *(t.lot for t in self.aval)]

    @property
    def quantite_en_stock(self) -> Decimal:
        """Ce qui n'est pas encore parti : à retenir à l'usine."""
        return self.quantite_produite - self.quantite_expediee


def livraisons_par_client(lots_finis) -> list[LivraisonClient]:
    """Qui a reçu quoi, parmi ces lots : la liste des clients à prévenir."""
    lignes = (
        LigneExpedition.objects.filter(lot__in=lots_finis)
        .select_related("expedition__client", "lot__article")
        .order_by("expedition__client__nom", "expedition__date", "lot__numero")
    )
    par_client: dict[int, LivraisonClient] = {}
    for ligne in lignes:
        client = ligne.expedition.client
        livraison = par_client.setdefault(
            client.pk, LivraisonClient(client.pk, client.nom, client.ville, client.adresse, client.email)
        )
        livraison.lignes.append(ligne)
    return list(par_client.values())


def mesurer_impact(lot: Lot) -> Impact:
    aval = lots_en_aval(lot)
    concernes = [lot, *(t.lot for t in aval)]
    lots_finis = [l for l in concernes if l.article.nature == Article.Nature.FINI]
    clients = livraisons_par_client(lots_finis)
    return Impact(
        origine=lot,
        aval=aval,
        lots_finis=lots_finis,
        clients=clients,
        quantite_produite=sum((l.quantite for l in lots_finis), Decimal(0)),
        quantite_expediee=sum((l.quantite for c in clients for l in c.lignes), Decimal(0)),
    )


@dataclass
class Noeud:
    """Un lot dans l'arbre affiché, avec la quantité qui le relie à son parent."""

    lot: Lot
    quantite: Decimal | None
    unite: str
    enfants: list["Noeud"]


def arbre(lot: Lot, *, vers_l_aval: bool) -> Noeud:
    """La chaîne sous forme d'arbre, pour l'affichage. Un lot partagé apparaît sous chacun de ses parents."""
    traces = _parcourir(lot, vers_l_aval=vers_l_aval)
    lots = {lot.pk: lot, **{t.lot.pk: t.lot for t in traces}}
    liens = Composition.objects.filter(lot_produit_id__in=lots, lot_utilise_id__in=lots)
    enfants: dict[int, list[tuple[int, Decimal]]] = defaultdict(list)
    for c in liens:
        depart, arrivee = (c.lot_utilise_id, c.lot_produit_id) if vers_l_aval else (c.lot_produit_id, c.lot_utilise_id)
        enfants[depart].append((arrivee, c.quantite))

    def construire(lot_id: int, quantite, unite: str, chemin: frozenset) -> Noeud:
        suite = [
            # La quantité est toujours celle du lot utilisé : du parent en aval, de l'enfant en amont.
            construire(e, q, (lots[lot_id] if vers_l_aval else lots[e]).article.get_unite_display(), chemin | {e})
            for e, q in sorted(enfants[lot_id], key=lambda x: lots[x[0]].numero)
            if e not in chemin
        ]
        return Noeud(lots[lot_id], quantite, unite, suite)

    return construire(lot.pk, None, "", frozenset({lot.pk}))


@transaction.atomic
def lancer_rappel(lot: Lot, *, motif: str, niveau: str, par=None) -> Rappel:
    """Crée le rappel et bloque d'un coup le lot d'origine et tout ce qui en descend."""
    impact = mesurer_impact(lot)
    annee = timezone.localdate().year
    rang = Rappel.objects.filter(numero__startswith=f"RAP-{annee}-").count() + 1
    rappel = Rappel.objects.create(
        numero=f"RAP-{annee}-{rang:03d}", lot_origine=lot, motif=motif, niveau=niveau, cree_par=par
    )
    rappel.lots_bloques.set(impact.lots_a_bloquer)
    return rappel


def clore_rappel(rappel: Rappel) -> None:
    """Le rappel est terminé : ses lots ne sont plus bloqués (sauf par un autre rappel ouvert)."""
    rappel.statut = Rappel.Statut.CLOS
    rappel.clos_le = timezone.now()
    rappel.save(update_fields=["statut", "clos_le"])
