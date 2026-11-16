from django import forms

from .models import Rappel


class RappelForm(forms.ModelForm):
    class Meta:
        model = Rappel
        fields = ["motif", "niveau"]
        widgets = {
            "motif": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Ex. : alerte du fournisseur, présence de Listeria sur le lot V-2210."}
            ),
            "niveau": forms.RadioSelect,
        }
