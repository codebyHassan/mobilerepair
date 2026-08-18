from django import forms
from .models import Customer, Device

import re

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'whatsapp', 'email', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number (e.g. 03001234567)'}),
            'whatsapp': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'WhatsApp Number (e.g. 03001234567)'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address (optional)'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Home/Work Address', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'General Notes', 'rows': 3}),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '')
        if phone:
            digits = re.sub(r'\D', '', str(phone))
            if len(digits) < 10 or len(digits) > 13:
                raise forms.ValidationError("Please enter a valid phone number (e.g. 03001234567).")
        return phone

    def clean_whatsapp(self):
        whatsapp = self.cleaned_data.get('whatsapp', '')
        if whatsapp:
            digits = re.sub(r'\D', '', str(whatsapp))
            if len(digits) < 10 or len(digits) > 13:
                raise forms.ValidationError("Please enter a valid WhatsApp number (e.g. 03001234567).")
        return whatsapp

class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = [
            'brand', 'model', 'imei', 'serial_number', 'color', 
            'storage', 'network_info', 'device_password', 
            'physical_condition', 'accessories_received', 'notes'
        ]
        widgets = {
            'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Apple, Samsung'}),
            'model': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. iPhone 13, Galaxy S23'}),
            'imei': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IMEI (optional)'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Serial Number (optional)'}),
            'color': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Black, White'}),
            'storage': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 128GB, 256GB'}),
            'network_info': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Unlocked, Locked to network'}),
            'device_password': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Lock Pattern, PIN or Password'}),
            'physical_condition': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'e.g. Screen cracked, Back glass broken', 'rows': 2}),
            'accessories_received': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'e.g. SIM Tray, Box, Charger', 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Other technical device notes', 'rows': 2}),
        }
