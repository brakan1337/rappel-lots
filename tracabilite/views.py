from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import RappelForm
from .models import Article, Lot, Rappel
from .tracage import arbre, clore_rappel, lancer_rappel, livraisons_par_client, mesurer_impact


@login_required
def accueil(request):
    recherche = request.GET.get("q", "").strip()
    resultats = []
    if recherche:
        resultats = list(
            Lot.objects.filter(
                Q(numero__icontains=recherche) | Q(numero_fournisseur__icontains=recherche)
            ).select_related("article", "fournisseur")[:30]
        )
        if len(resultats) == 1:
            return redirect("tracabilite:lot", numero=resultats[0].numero)
    return render(
        request,
        "tracabilite/accueil.html",
        {
            "recherche": recherche,
            "resultats": resultats,
            "rappels_ouverts": Rappel.objects.filter(statut=Rappel.Statut.OUVERT)
            .select_related("lot_origine__article")
            .annotate(nb_lots=Count("lots_bloques")),
            "nb_lots_bloques": Lot.objects.bloques().count(),
            "derniers_lots_matiere": Lot.objects.filter(article__nature=Article.Nature.MATIERE).select_related(
                "article", "fournisseur"
            )[:8],
        },
    )


@login_required
def fiche_lot(request, numero):
    lot = get_object_or_404(Lot.objects.select_related("article", "fournisseur"), numero=numero)
    formulaire = RappelForm(request.POST or None)

    if request.method == "POST":
        if not request.user.has_perm("tracabilite.add_rappel"):
            raise PermissionDenied("Seul le service qualité peut lancer un rappel.")
        if formulaire.is_valid():
            rappel = lancer_rappel(
                lot, motif=formulaire.cleaned_data["motif"], niveau=formulaire.cleaned_data["niveau"], par=request.user
            )
            messages.success(request, f"Rappel {rappel.numero} lancé : {rappel.lots_bloques.count()} lots bloqués.")
            return redirect("tracabilite:rappel", numero=rappel.numero)

    return render(
        request,
        "tracabilite/lot.html",
        {
            "lot": lot,
            "amont": arbre(lot, vers_l_aval=False),
            "aval": arbre(lot, vers_l_aval=True),
            "impact": mesurer_impact(lot),
            "rappels": lot.rappels.all(),
            "formulaire": formulaire,
            "peut_rappeler": request.user.has_perm("tracabilite.add_rappel"),
        },
    )


@login_required
def liste_rappels(request):
    rappels = Rappel.objects.select_related("lot_origine__article").annotate(nb_lots=Count("lots_bloques"))
    return render(request, "tracabilite/rappels.html", {"rappels": rappels})


def _contexte_rappel(rappel):
    lots = rappel.lots_bloques.select_related("article").order_by("article__nature", "numero")
    finis = [l for l in lots if l.article.nature == Article.Nature.FINI]
    return {"rappel": rappel, "lots": lots, "lots_finis": finis, "clients": livraisons_par_client(finis)}


@login_required
def detail_rappel(request, numero):
    rappel = get_object_or_404(Rappel.objects.select_related("lot_origine__article", "cree_par"), numero=numero)
    return render(request, "tracabilite/rappel.html", _contexte_rappel(rappel))


@login_required
@require_POST
def clore(request, numero):
    if not request.user.has_perm("tracabilite.change_rappel"):
        raise PermissionDenied("Seul le service qualité peut clore un rappel.")
    rappel = get_object_or_404(Rappel, numero=numero, statut=Rappel.Statut.OUVERT)
    clore_rappel(rappel)
    messages.success(request, f"Rappel {rappel.numero} clos : ses lots sont débloqués.")
    return redirect("tracabilite:rappel", numero=numero)


@login_required
def courriers(request, numero):
    rappel = get_object_or_404(Rappel.objects.select_related("lot_origine__article"), numero=numero)
    contexte = _contexte_rappel(rappel)
    contexte["date_courrier"] = timezone.localdate()
    return render(request, "tracabilite/courriers.html", contexte)
