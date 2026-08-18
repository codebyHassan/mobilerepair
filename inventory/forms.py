from django import forms
from .models import Part, InventoryTransaction, Supplier, SupplierPayment

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'phone', 'whatsapp', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier/Vendor Name (e.g. Ali Parts Market)'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'whatsapp': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'WhatsApp Number'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Shop Address / Market Location'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Notes / Payment terms...', 'rows': 2}),
        }

class SupplierPaymentForm(forms.ModelForm):
    class Meta:
        model = SupplierPayment
        fields = ['amount', 'payment_method', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Amount in Rs.'}),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Payment reference / receipt note...', 'rows': 2}),
        }

class PartForm(forms.ModelForm):
    class Meta:
        model = Part
        fields = [
            'name', 'sku', 'brand', 'compatible_device', 'category',
            'purchase_cost', 'selling_price', 'current_stock', 'minimum_stock', 'supplier_fk', 'is_credit_purchase', 'notes'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Part Name (e.g. iPhone 13 OLED Display)'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SKU/Unique identifier'}),
            'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. OEM, Apple, Samsung'}),
            'compatible_device': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. iPhone 13, A2633'}),
            'category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Screen, Battery, Charging Port'}),
            'purchase_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'current_stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'minimum_stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'supplier_fk': forms.Select(attrs={'class': 'form-control'}),
            'is_credit_purchase': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Part storage location, bin #, warranty info...', 'rows': 2}),
        }

class InventoryTransactionForm(forms.ModelForm):
    class Meta:
        model = InventoryTransaction
        fields = ['transaction_type', 'quantity', 'note']
        widgets = {
            'transaction_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Reason for adjustment...', 'rows': 2}),
        }
