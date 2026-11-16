"""
Le modèle de traçabilité.

Tout ce qui entre ou sort de l'usine est un *lot* : un lot de matière première reçu
d'un fournisseur, un lot de produit intermédiaire (une sauce, un fond), un lot de
produit fini. Une *composition* dit qu'un lot a servi à fabriquer un autre lot.
Ces liens forment un graphe qu'on remonte (amont) ou qu'on descend (aval).
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Exists, OuterRef


class Fournisseur(models.Model):
    nom = models.CharField(max_length=120, unique=True)
    ville = models.CharField(max_length=80)
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Client(models.Model):
    nom = models.CharField(max_length=120, unique=True)
    ville = models.CharField(max_length=80)
    adresse = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Article(models.Model):
    class Nature(models.TextChoices):
        MATIERE = "MATIERE", "Matière première"
        INTERMEDIAIRE = "INTERMEDIAIRE", "Produit intermédiaire"
        FINI = "FINI", "Produit fini"

    class Unite(models.TextChoices):
        KG = "KG", "kg"
        UNITE = "UNITE", "unités"

    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=120)
    nature = models.CharField(max_length=15, choices=Nature)
    unite = models.CharField(max_length=5, choices=Unite, default=Unite.KG)

    class Meta:
        ordering = ["nature", "libelle"]

    def __str__(self):
        return self.libelle


class LotQuerySet(models.QuerySet):
    def bloques(self):
        """Les lots retenus par au moins un rappel encore ouvert."""
        rappels_ouverts = Rappel.lots_bloques.through.objects.filter(
            lot_id=OuterRef("pk"), rappel__statut=Rappel.Statut.OUVERT
        )
        return self.filter(Exists(rappels_ouverts))


class Lot(models.Model):
    numero = models.CharField("numéro", max_length=40, unique=True)
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name="lots")
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.PROTECT, related_name="lots", null=True, blank=True)
    numero_fournisseur = models.CharField("n° de lot fournisseur", max_length=40, blank=True)
    date = models.DateField(help_text="Date de réception ou de fabrication.")
    dlc = models.DateField("DLC", help_text="Date limite de consommation.")
    quantite = models.DecimalField("quantité", max_digits=10, decimal_places=2)

    objects = LotQuerySet.as_manager()

    class Meta:
        ordering = ["-date", "numero"]
        indexes = [models.Index(fields=["numero_fournisseur"])]

    def __str__(self):
        return self.numero

    def clean(self):
        est_matiere = self.article_id and self.article.nature == Article.Nature.MATIERE
        if est_matiere and not self.fournisseur_id:
            raise ValidationError({"fournisseur": "Une matière première vient forcément d'un fournisseur."})
        if not est_matiere and self.fournisseur_id:
            raise ValidationError({"fournisseur": "Un lot fabriqué ici n'a pas de fournisseur."})
        if self.dlc and self.date and self.dlc < self.date:
            raise ValidationError({"dlc": "La DLC ne peut pas précéder la date du lot."})

    @property
    def est_bloque(self) -> bool:
        return self.rappels.filter(statut=Rappel.Statut.OUVERT).exists()


class Composition(models.Model):
    """Le lot *utilisé* est entré dans la fabrication du lot *produit*."""

    lot_produit = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name="entrees")
    lot_utilise = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="utilisations")
    quantite = models.DecimalField("quantité utilisée", max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["lot_produit", "lot_utilise"], name="composition_unique"),
            models.CheckConstraint(
                condition=~models.Q(lot_produit=models.F("lot_utilise")),
                name="composition_pas_sur_soi_meme",
            ),
        ]

    def __str__(self):
        return f"{self.lot_utilise} → {self.lot_produit}"

    def clean(self):
        if not (self.lot_produit_id and self.lot_utilise_id):
            return
        if self.lot_produit.article.nature == Article.Nature.MATIERE:
            raise ValidationError("Une matière première ne se fabrique pas : elle se reçoit.")
        if self.lot_utilise.date > self.lot_produit.date:
            raise ValidationError("Un lot ne peut pas servir avant d'avoir été reçu ou fabriqué.")


class Expedition(models.Model):
    numero = models.CharField("bon de livraison", max_length=30, unique=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="expeditions")
    date = models.DateField()

    class Meta:
        ordering = ["-date", "numero"]
        verbose_name = "expédition"

    def __str__(self):
        return self.numero


class LigneExpedition(models.Model):
    expedition = models.ForeignKey(Expedition, on_delete=models.CASCADE, related_name="lignes")
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="expeditions")
    quantite = models.DecimalField("quantité", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "ligne d'expédition"
        verbose_name_plural = "lignes d'expédition"

    def __str__(self):
        return f"{self.expedition} : {self.lot}"

    def clean(self):
        if not self.lot_id:
            return
        if self.lot.article.nature != Article.Nature.FINI:
            raise ValidationError({"lot": "Seuls les produits finis s'expédient."})
        if self.lot.est_bloque:
            raise ValidationError({"lot": f"Le lot {self.lot} est bloqué par un rappel en cours."})


class Rappel(models.Model):
    class Niveau(models.TextChoices):
        RETRAIT = "RETRAIT", "Retrait : les produits sont retirés de la vente"
        RAPPEL = "RAPPEL", "Rappel : les consommateurs sont aussi prévenus"

    class Statut(models.TextChoices):
        OUVERT = "OUVERT", "Ouvert"
        CLOS = "CLOS", "Clos"

    numero = models.CharField("numéro", max_length=20, unique=True)
    lot_origine = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="rappels_declenches")
    motif = models.TextField()
    niveau = models.CharField(max_length=10, choices=Niveau, default=Niveau.RETRAIT)
    statut = models.CharField(max_length=10, choices=Statut, default=Statut.OUVERT)
    cree_le = models.DateTimeField("créé le", auto_now_add=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    clos_le = models.DateTimeField("clos le", null=True, blank=True)
    lots_bloques = models.ManyToManyField(Lot, related_name="rappels", verbose_name="lots bloqués")

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return self.numero
