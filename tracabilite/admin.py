"""
Le back-office du service qualité.

C'est la raison du choix de Django : l'administration générée donne à l'équipe
de quoi saisir et chercher fournisseurs, lots et expéditions sans écrire d'écran.
"""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    Article,
    Client,
    Composition,
    Expedition,
    Fournisseur,
    LigneExpedition,
    Lot,
    Rappel,
)

admin.site.site_header = "Traçabilité et rappels de lots"
admin.site.site_title = "Rappels de lots"
admin.site.index_title = "Back-office qualité"


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ["nom", "ville", "email"]
    search_fields = ["nom", "ville"]


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["nom", "ville", "email"]
    search_fields = ["nom", "ville"]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ["code", "libelle", "nature", "unite"]
    list_filter = ["nature"]
    search_fields = ["code", "libelle"]


class EntreeInline(admin.TabularInline):
    model = Composition
    fk_name = "lot_produit"
    extra = 0
    autocomplete_fields = ["lot_utilise"]
    verbose_name = "lot utilisé"
    verbose_name_plural = "Lots utilisés pour fabriquer ce lot"


class EstBloqueFiltre(admin.SimpleListFilter):
    title = "blocage"
    parameter_name = "bloque"

    def lookups(self, request, model_admin):
        return [("oui", "Bloqués par un rappel"), ("non", "Libres")]

    def queryset(self, request, queryset):
        if self.value() == "oui":
            return queryset.bloques()
        if self.value() == "non":
            return queryset.exclude(pk__in=Lot.objects.bloques())
        return queryset


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = ["numero", "article", "nature", "date", "dlc", "quantite", "fournisseur", "fiche"]
    list_filter = ["article__nature", EstBloqueFiltre, "fournisseur", "date"]
    search_fields = ["numero", "numero_fournisseur", "article__libelle"]
    date_hierarchy = "date"
    autocomplete_fields = ["article", "fournisseur"]
    list_select_related = ["article", "fournisseur"]
    inlines = [EntreeInline]

    @admin.display(description="nature", ordering="article__nature")
    def nature(self, lot):
        return lot.article.get_nature_display()

    @admin.display(description="traçabilité")
    def fiche(self, lot):
        return format_html('<a href="{}">Voir la chaîne</a>', reverse("tracabilite:lot", args=[lot.numero]))


class LigneExpeditionInline(admin.TabularInline):
    model = LigneExpedition
    extra = 1
    autocomplete_fields = ["lot"]


@admin.register(Expedition)
class ExpeditionAdmin(admin.ModelAdmin):
    list_display = ["numero", "client", "date"]
    list_filter = ["date", "client"]
    search_fields = ["numero", "client__nom", "lignes__lot__numero"]
    date_hierarchy = "date"
    autocomplete_fields = ["client"]
    inlines = [LigneExpeditionInline]


@admin.register(Rappel)
class RappelAdmin(admin.ModelAdmin):
    list_display = ["numero", "lot_origine", "niveau", "statut", "cree_le", "nombre_lots"]
    list_filter = ["statut", "niveau"]
    search_fields = ["numero", "lot_origine__numero", "motif"]
    readonly_fields = ["numero", "lot_origine", "cree_le", "cree_par", "clos_le", "lots_bloques"]
    fields = ["numero", "lot_origine", "motif", "niveau", "statut", "cree_le", "cree_par", "clos_le", "lots_bloques"]

    @admin.display(description="lots bloqués")
    def nombre_lots(self, rappel):
        return rappel.lots_bloques.count()

    def has_add_permission(self, request):
        # Un rappel se lance depuis la fiche d'un lot, qui calcule ce qu'il faut bloquer.
        return False
