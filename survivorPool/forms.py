from django import forms
from .models import Pick

CHOICES = ((1, 1), (2, 2), (3, 3), (4, 4),
           (5, 5), (6, 6), (7, 7), (8, 8),
           (9, 9), (10, 10), (11, 11), (12, 12))

class PostForm(forms.ModelForm):
    week = forms.ChoiceField(choices=CHOICES)
    class Meta:
        model = Pick
        fields = ("team", "week", "user_name",)
        
        widgets = {
            "team": forms.Select(attrs={"class": "form-control"}),
            "user_name": forms.TextInput(attrs={"class": "form-control", "value": "", "id": "user", "type": "hidden"}),
            #"user_name": forms.Select(attrs={"class": "form-control"}, ),
            "week": forms.Select(choices=CHOICES, attrs={"class": "form-control"})
        }