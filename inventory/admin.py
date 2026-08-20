from django.contrib import admin
from django.contrib import messages
from .models import Part, InventoryTransaction, RepairPart, Supplier, SupplierPayment


# ─── SUPPLIER PAYMENT INLINE ────────────────────────────────────────────────────

class SupplierPaymentInline(admin.TabularInline):
    model = SupplierPayment
    extra = 0
    readonly_fields = ('created_at', 'paid_by')
    fields = ('amount', 'payment_method', 'notes', 'paid_by', 'created_at')


# ─── INVENTORY TRANSACTION INLINE ───────────────────────────────────────────────

class InventoryTransactionInline(admin.TabularInline):
    model = InventoryTransaction
    extra = 0
    readonly_fields = ('transaction_type', 'quantity', 'repair_job', 'created_by', 'created_at', 'note')
    can_delete = False


# ─── SUPPLIER ───────────────────────────────────────────────────────────────────

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'whatsapp', 'address', 'due_balance_display', 'created_at')
    search_fields = ('name', 'phone', 'whatsapp', 'address')
    inlines = [SupplierPaymentInline]
    ordering = ('name',)

    @admin.display(description='Udhar Balance (Rs.)')
    def due_balance_display(self, obj):
        from django.utils.html import format_html
        bal = obj.due_balance
        if bal > 0:
            return format_html('<span style="color:red; font-weight:bold;">Rs. {}</span>', f"{bal:,.0f}")
        return format_html('<span style="color:green;">✅ Cleared</span>')


# ─── SUPPLIER PAYMENT ────────────────────────────────────────────────────────────

@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'amount', 'payment_method', 'paid_by', 'notes', 'created_at')
    list_filter = ('payment_method', 'created_at')
    search_fields = ('supplier__name', 'notes')
    readonly_fields = ('created_at', 'paid_by')
    ordering = ('-created_at',)


# ─── PART ────────────────────────────────────────────────────────────────────────

@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'category', 'brand', 'purchase_cost', 'selling_price', 'current_stock', 'minimum_stock', 'stock_status', 'supplier_fk')
    list_filter = ('category', 'brand', 'created_at')
    search_fields = ('sku', 'name', 'compatible_device', 'category', 'brand', 'supplier_fk__name')
    list_editable = ('purchase_cost', 'selling_price', 'current_stock', 'minimum_stock')
    autocomplete_fields = ['supplier_fk']
    inlines = [InventoryTransactionInline]
    ordering = ('name',)
    actions = ['add_10_stock']

    @admin.display(description='Stock Status')
    def stock_status(self, obj):
        from django.utils.html import format_html
        if obj.current_stock <= 0:
            return format_html('<span style="color:red; font-weight:bold;">🔴 OUT OF STOCK</span>')
        if obj.current_stock <= obj.minimum_stock:
            return format_html('<span style="color:orange; font-weight:bold;">🟡 LOW STOCK</span>')
        return format_html('<span style="color:green;">🟢 OK</span>')

    @admin.action(description="📦 Add +10 stock to selected parts")
    def add_10_stock(self, request, queryset):
        for part in queryset:
            part.current_stock += 10
            part.save()
            InventoryTransaction.objects.create(
                part=part,
                transaction_type='purchase',
                quantity=10,
                note='Admin Bulk Action: +10 Stock Added',
                created_by=request.user
            )
        self.message_user(request, f"Added +10 units to {queryset.count()} selected parts.", messages.SUCCESS)


# ─── INVENTORY TRANSACTION ───────────────────────────────────────────────────────

@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ('part', 'transaction_type', 'quantity', 'repair_job', 'created_by', 'created_at', 'note')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('part__name', 'part__sku', 'repair_job__job_number')
    autocomplete_fields = ['part', 'repair_job']
    ordering = ('-created_at',)


# ─── REPAIR PART ─────────────────────────────────────────────────────────────────

@admin.register(RepairPart)
class RepairPartAdmin(admin.ModelAdmin):
    list_display = ('repair_job', 'part', 'quantity', 'purchase_cost', 'customer_price', 'added_at')
    search_fields = ('repair_job__job_number', 'part__name', 'part__sku', 'repair_job__customer__name')
    autocomplete_fields = ['repair_job', 'part']
    ordering = ('-added_at',)
