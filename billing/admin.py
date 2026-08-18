from django.contrib import admin
from django.utils.html import format_html
from .models import Invoice, Payment


# ─── PAYMENT INLINE ─────────────────────────────────────────────────────────────

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ('created_at', 'received_by')
    fields = ('amount', 'payment_method', 'notes', 'received_by', 'created_at')


# ─── INVOICE ────────────────────────────────────────────────────────────────────

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'repair_job', 'subtotal', 'discount', 'total', 'paid_amount', 'due_amount_display', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('invoice_number', 'repair_job__job_number', 'repair_job__customer__name', 'repair_job__customer__phone')
    readonly_fields = ('invoice_number', 'subtotal', 'total', 'paid_amount', 'due_amount', 'created_at', 'updated_at')
    inlines = [PaymentInline]
    ordering = ('-created_at',)
    list_per_page = 30

    @admin.display(description='Balance Due', ordering='due_amount')
    def due_amount_display(self, obj):
        if obj.due_amount > 0:
            return format_html('<span style="color:red; font-weight:bold;">Rs. {}</span>', f"{obj.due_amount:,.2f}")
        return format_html('<span style="color:green; font-weight:bold;">✅ Cleared</span>')


# ─── PAYMENT ────────────────────────────────────────────────────────────────────

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoice', 'amount', 'payment_method', 'received_by', 'notes', 'created_at')
    list_filter = ('payment_method', 'created_at')
    search_fields = ('invoice__invoice_number', 'invoice__repair_job__job_number', 'invoice__repair_job__customer__name')
    readonly_fields = ('created_at', 'received_by')
    ordering = ('-created_at',)
