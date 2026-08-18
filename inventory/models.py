from django.db import models
from django.contrib.auth.models import User
from repairs.models import RepairJob

class Supplier(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    phone = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    whatsapp = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def total_purchases_value(self):
        from django.db.models import Sum
        total = 0.00
        for part in self.parts.filter(is_credit_purchase=True):
            qty_used = part.repair_uses.aggregate(s=Sum('quantity'))['s'] or 0
            total_qty = part.current_stock + qty_used
            if total_qty == 0:
                total_qty = 1
            total += float(part.purchase_cost) * total_qty
        return total

    @property
    def total_paid(self):
        from django.db.models import Sum
        return float(self.payments.aggregate(total=Sum('amount'))['total'] or 0.00)

    @property
    def due_balance(self):
        return max(0.00, float(self.total_purchases_value) - float(self.total_paid))

class SupplierPayment(models.Model):
    PAYMENT_METHODS = [
        ('CASH', 'Cash'),
        ('JAZZCASH', 'JazzCash'),
        ('EASYPAISA', 'EasyPaisa'),
        ('BANK', 'Bank Transfer'),
        ('OTHER', 'Other'),
    ]
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='CASH')
    notes = models.TextField(blank=True, null=True)
    paid_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment Rs. {self.amount} to {self.supplier.name}"

class Part(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    sku = models.CharField(max_length=100, unique=True, db_index=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    compatible_device = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    category = models.CharField(max_length=100, db_index=True)
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    current_stock = models.PositiveIntegerField(default=0, db_index=True)
    minimum_stock = models.PositiveIntegerField(default=0)
    supplier = models.CharField(max_length=255, blank=True, null=True)
    supplier_fk = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='parts')
    is_credit_purchase = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.sku})"

class InventoryTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('purchase', 'Purchase'),
        ('repair_use', 'Used in Repair'),
        ('adjustment', 'Adjustment'),
        ('return', 'Return'),
        ('damaged', 'Damaged'),
    ]
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField()  # Positive for additions, Negative for subtractions
    repair_job = models.ForeignKey(RepairJob, on_delete=models.CASCADE, null=True, blank=True, related_name='inventory_transactions')
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.transaction_type.upper()} - {self.part.name} ({self.quantity})"

class RepairPart(models.Model):
    repair_job = models.ForeignKey(RepairJob, on_delete=models.CASCADE, related_name='parts_used')
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='repair_uses')
    quantity = models.PositiveIntegerField(default=1)
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2)  # price of part at purchase time
    customer_price = models.DecimalField(max_digits=12, decimal_places=2)  # price charged to customer
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.part.name} x{self.quantity} in {self.repair_job.job_number}"
