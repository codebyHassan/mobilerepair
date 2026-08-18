from django.contrib import admin
from django.utils.html import format_html
from .models import ShopSetting, AuditLog

admin.site.site_header = "TechCare Mobile Repair Shop Management"
admin.site.site_title = "Shop Admin Portal"
admin.site.index_title = "Mobile Repair Shop Operations & System Control Center"


# ─── SHOP SETTING ────────────────────────────────────────────────────────────────

@admin.register(ShopSetting)
class ShopSettingAdmin(admin.ModelAdmin):
    list_display = ('shop_name', 'shop_phone', 'currency', 'invoice_prefix', 'job_prefix')
    fieldsets = (
        ('Shop Branding & Info', {
            'fields': ('shop_name', 'shop_phone', 'shop_address', 'shop_logo')
        }),
        ('Invoice & Job System Prefixes', {
            'fields': ('currency', 'invoice_prefix', 'job_prefix')
        }),
    )


# ─── AUDIT LOG ───────────────────────────────────────────────────────────────────

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action_badge', 'model_name', 'object_repr', 'ip_address', 'details_short')
    list_filter = ('action', 'model_name', 'timestamp')
    search_fields = ('user__username', 'model_name', 'object_repr', 'details', 'ip_address')
    readonly_fields = ('user', 'action', 'model_name', 'object_id', 'object_repr', 'details', 'ip_address', 'timestamp')
    ordering = ('-timestamp',)
    list_per_page = 50
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False  # Audit logs are read-only — never manually added

    def has_change_permission(self, request, obj=None):
        return False  # Immutable

    @admin.display(description='Action')
    def action_badge(self, obj):
        colors = {
            'CREATE': '#16a34a',
            'UPDATE': '#2563eb',
            'DELETE': '#dc2626',
            'STATUS_CHANGE': '#d97706',
            'PAYMENT': '#7c3aed',
            'WHATSAPP': '#059669',
            'LOGIN': '#0891b2',
            'OTHER': '#6b7280',
        }
        color = colors.get(obj.action, '#6b7280')
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:10px; font-size:0.78rem; font-weight:600;">{}</span>',
            color, obj.action
        )

    @admin.display(description='Details')
    def details_short(self, obj):
        if obj.details:
            return obj.details[:80] + ('…' if len(obj.details) > 80 else '')
        return '—'
