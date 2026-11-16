"""
L'API des entrepôts.

Avant de charger un camion, le logiciel de l'entrepôt interroge l'usine : ce lot
est-il bloqué ? Il déclare ensuite l'expédition, que l'API refuse si un lot est retenu.
"""

from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..models import Article, Expedition, Lot, Rappel
from ..tracage import livraisons_par_client, lots_en_amont, lots_en_aval
from .serializers import (
    ClientAPrevenirSerializer,
    ExpeditionSerializer,
    LotSerializer,
    LotTraceSerializer,
    RappelSerializer,
)


class LotDetail(generics.RetrieveAPIView):
    queryset = Lot.objects.select_related("article", "fournisseur").prefetch_related("rappels")
    serializer_class = LotSerializer
    lookup_field = "numero"


@api_view(["GET"])
def lots_bloques(request):
    """La liste à jour des lots interdits d'expédition, pour la synchronisation des entrepôts."""
    return Response(sorted(Lot.objects.bloques().values_list("numero", flat=True)))


@api_view(["GET"])
def aval(request, numero):
    lot = get_object_or_404(Lot, numero=numero)
    return Response(LotTraceSerializer(lots_en_aval(lot), many=True).data)


@api_view(["GET"])
def amont(request, numero):
    lot = get_object_or_404(Lot, numero=numero)
    return Response(LotTraceSerializer(lots_en_amont(lot), many=True).data)


class RappelListe(generics.ListAPIView):
    serializer_class = RappelSerializer

    def get_queryset(self):
        rappels = Rappel.objects.select_related("lot_origine").prefetch_related("lots_bloques")
        statut = self.request.query_params.get("statut")
        return rappels.filter(statut=statut.upper()) if statut else rappels


@api_view(["GET"])
def rappel_detail(request, numero):
    rappel = get_object_or_404(Rappel.objects.select_related("lot_origine"), numero=numero)
    finis = rappel.lots_bloques.filter(article__nature=Article.Nature.FINI)
    donnees = RappelSerializer(rappel).data
    donnees["clients_a_prevenir"] = ClientAPrevenirSerializer(livraisons_par_client(finis), many=True).data
    return Response(donnees)


class ExpeditionCreation(generics.CreateAPIView):
    queryset = Expedition.objects.all()
    serializer_class = ExpeditionSerializer
