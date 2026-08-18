from django import forms
from .models import Technician, RepairJob, Diagnosis, RepairEstimate

class TechnicianForm(forms.ModelForm):
    class Meta:
        model = Technician
        fields = ['user', 'name', 'phone', 'specialization', 'default_commission_rate', 'status']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Technician Name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'specialization': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Micro-soldering, Screen replacements'}),
            'default_commission_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Default Commission % (e.g. 10)'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

class RepairJobForm(forms.ModelForm):
    class Meta:
        model = RepairJob
        fields = [
            'complaint', 'physical_condition', 'accessories', 
            'expected_delivery_date', 'priority', 'assigned_technician', 'notes'
        ]
        widgets = {
            'complaint': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Describe customer complaint...', 'rows': 3}),
            'physical_condition': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Initial physical inspection...', 'rows': 2}),
            'accessories': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'List accessories kept: SIM Tray, box, case, charger...', 'rows': 2}),
            'expected_delivery_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'assigned_technician': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Additional job comments...', 'rows': 2}),
        }

class DiagnosisForm(forms.ModelForm):
    class Meta:
        model = Diagnosis
        fields = ['technician_diagnosis', 'recommended_repair']
        widgets = {
            'technician_diagnosis': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Enter technical diagnosis findings...', 'rows': 3}),
            'recommended_repair': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Describe recommended repair actions...', 'rows': 3}),
        }

class RepairEstimateForm(forms.ModelForm):
    class Meta:
        model = RepairEstimate
        fields = ['estimated_cost', 'status', 'rejection_reason']
        widgets = {
            'estimated_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'required': 'required', 'min': '0'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'rejection_reason': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'If rejected, note why...', 'rows': 2}),
        }

    def clean_estimated_cost(self):
        cost = self.cleaned_data.get('estimated_cost')
        if cost is None:
            raise forms.ValidationError("Estimated Cost is required and cannot be empty.")
        if cost < 0:
            raise forms.ValidationError("Estimated Cost cannot be negative.")
        return cost
