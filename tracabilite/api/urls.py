from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    # « bloques » avant « <numero> », sinon il serait lu comme un numéro de lot.
    path("lots/bloques/", views.lots_bloques, name="lots-bloques"),
    path("lots/<str:numero>/", views.LotDetail.as_view(), name="lot"),
    path("lots/<str:numero>/aval/", views.aval, name="aval"),
    path("lots/<str:numero>/amont/", views.amont, name="amont"),
    path("rappels/", views.RappelListe.as_view(), name="rappels"),
    path("rappels/<str:numero>/", views.rappel_detail, name="rappel"),
    path("expeditions/", views.ExpeditionCreation.as_view(), name="expeditions"),
]
