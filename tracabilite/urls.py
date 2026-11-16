from django.urls import path

from . import views

app_name = "tracabilite"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("lots/<str:numero>/", views.fiche_lot, name="lot"),
    path("rappels/", views.liste_rappels, name="rappels"),
    path("rappels/<str:numero>/", views.detail_rappel, name="rappel"),
    path("rappels/<str:numero>/clore/", views.clore, name="clore"),
    path("rappels/<str:numero>/courriers/", views.courriers, name="courriers"),
]
