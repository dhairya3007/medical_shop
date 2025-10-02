from django import forms
from .models import Medicine

class MedicineForm(forms.ModelForm):
    class Meta:
        model = Medicine
        fields = '__all__'
        widgets = {
            'components': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter active ingredients and components'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Paracetamol Tablets'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., PharmaCorp Inc.'}),
            'power': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 500mg'}),
            'product_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., PC-12345'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }