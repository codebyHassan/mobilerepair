from django.db import models
from django.contrib.auth.models import User
from repairs.models import RepairJob

class Invoice(models.Model):
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True)
    repair_job = models.OneToOneField(RepairJob, on_delete=models.CASCADE, related_name='invoice')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    due_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.invoice_number} ({self.repair_job.job_number})"

    def save(self, *args, **kwargs):
        from decimal import Decimal
        self.subtotal = Decimal(str(self.subtotal))
        self.discount = Decimal(str(self.discount))
        self.total = self.subtotal - self.discount
        self.paid_amount = Decimal(str(self.paid_amount))
        self.due_amount = self.total - self.paid_amount
        super().save(*args, **kwargs)

class Payment(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('card', 'Card'),
        ('easypaisa', 'Easypaisa'),
        ('jazzcash', 'JazzCash'),
        ('other', 'Other'),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHODS, default='cash')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"Payment #{self.id} for {self.invoice.invoice_number} - {self.amount}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        inv = self.invoice
        payments_sum = inv.payments.aggregate(models.Sum('amount'))['amount__sum'] or 0.00
        inv.paid_amount = payments_sum
        inv.save()

    def delete(self, *args, **kwargs):
        inv = self.invoice
        super().delete(*args, **kwargs)
        if inv and Invoice.objects.filter(id=inv.id).exists():
            payments_sum = inv.payments.aggregate(models.Sum('amount'))['amount__sum'] or 0.00
            inv.paid_amount = payments_sum
            inv.save()
