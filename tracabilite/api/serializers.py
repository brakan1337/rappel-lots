from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from ..models import Article, Client, Expedition, LigneExpedition, Lot, Rappel


class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ["code", "libelle", "nature", "unite"]


class LotSerializer(serializers.ModelSerializer):
    article = ArticleSerializer()
    fournisseur = serializers.StringRelatedField()
    est_bloque = serializers.SerializerMethodField()
    rappels_ouverts = serializers.SerializerMethodField()

    class Meta:
        model = Lot
        fields = [
            "numero",
            "article",
            "fournisseur",
            "numero_fournisseur",
            "date",
            "dlc",
            "quantite",
            "est_bloque",
            "rappels_ouverts",
        ]

    def _ouverts(self, lot):
        return [r for r in lot.rappels.all() if r.statut == Rappel.Statut.OUVERT]

    def get_est_bloque(self, lot) -> bool:
        return bool(self._ouverts(lot))

    def get_rappels_ouverts(self, lot) -> list[str]:
        return [r.numero for r in self._ouverts(lot)]


class LotTraceSerializer(serializers.Serializer):
    numero = serializers.CharField(source="lot.numero")
    article = serializers.CharField(source="lot.article.libelle")
    nature = serializers.CharField(source="lot.article.nature")
    date = serializers.DateField(source="lot.date")
    profondeur = serializers.IntegerField()


class LigneLivreeSerializer(serializers.Serializer):
    expedition = serializers.CharField(source="expedition.numero")
    date = serializers.DateField(source="expedition.date")
    lot = serializers.CharField(source="lot.numero")
    produit = serializers.CharField(source="lot.article.libelle")
    quantite = serializers.DecimalField(max_digits=10, decimal_places=2)


class ClientAPrevenirSerializer(serializers.Serializer):
    nom = serializers.CharField()
    ville = serializers.CharField()
    email = serializers.CharField()
    lignes = LigneLivreeSerializer(many=True)


class RappelSerializer(serializers.ModelSerializer):
    lot_origine = serializers.CharField(source="lot_origine.numero")
    lots_bloques = serializers.SlugRelatedField(slug_field="numero", many=True, read_only=True)

    class Meta:
        model = Rappel
        fields = ["numero", "lot_origine", "motif", "niveau", "statut", "cree_le", "clos_le", "lots_bloques"]


class LigneExpeditionSerializer(serializers.Serializer):
    lot = serializers.SlugRelatedField(slug_field="numero", queryset=Lot.objects.select_related("article"))
    quantite = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))

    def validate_lot(self, lot):
        if lot.article.nature != Article.Nature.FINI:
            raise serializers.ValidationError("Seuls les produits finis s'expédient.")
        if lot.est_bloque:
            raise serializers.ValidationError(f"Le lot {lot.numero} est bloqué par un rappel en cours.")
        return lot


class ExpeditionSerializer(serializers.ModelSerializer):
    """Ce que l'entrepôt envoie au moment de charger le camion."""

    client = serializers.SlugRelatedField(slug_field="nom", queryset=Client.objects.all())
    lignes = LigneExpeditionSerializer(many=True)

    class Meta:
        model = Expedition
        fields = ["numero", "client", "date", "lignes"]

    def validate_lignes(self, lignes):
        if not lignes:
            raise serializers.ValidationError("Une expédition contient au moins une ligne.")
        return lignes

    @transaction.atomic
    def create(self, donnees):
        lignes = donnees.pop("lignes")
        expedition = Expedition.objects.create(**donnees)
        LigneExpedition.objects.bulk_create(LigneExpedition(expedition=expedition, **l) for l in lignes)
        return expedition

    def to_representation(self, expedition):
        return {
            "numero": expedition.numero,
            "client": expedition.client.nom,
            "date": expedition.date.isoformat(),
            "lignes": [{"lot": l.lot.numero, "quantite": str(l.quantite)} for l in expedition.lignes.all()],
        }
