from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from .models import (
    Technician, RepairJob, RepairStatusHistory, RepairStageHistory,
    Diagnosis, RepairEstimate, InitialInspectionRecord,
    QualityCheckRecord, TechnicianCommissionRecord, WarrantyRecord
)
from inventory.models import RepairPart


# ─── INLINES ────────────────────────────────────────────────────────────────────

class RepairStatusHistoryInline(admin.TabularInline):
    model = RepairStatusHistory
    extra = 0
    readonly_fields = ('old_status', 'new_status', 'changed_by', 'timestamp', 'note')
    can_delete = False

class RepairStageHistoryInline(admin.TabularInline):
    model = RepairStageHistory
    extra = 0
    readonly_fields = ('stage_code', 'stage_name', 'status', 'note', 'created_by', 'created_at')
    can_delete = False

class DiagnosisInline(admin.StackedInline):
    model = Diagnosis
    extra = 0

class RepairEstimateInline(admin.StackedInline):
    model = RepairEstimate
    extra = 0

class RepairPartInline(admin.TabularInline):
    model = RepairPart
    extra = 0
    autocomplete_fields = ['part']
    readonly_fields = ('purchase_cost',)

class QualityCheckInline(admin.TabularInline):
    model = QualityCheckRecord
    extra = 0

class WarrantyInline(admin.TabularInline):
    model = WarrantyRecord
    extra = 0

class CommissionInline(admin.TabularInline):
    model = TechnicianCommissionRecord
    extra = 0
    readonly_fields = ('gross_profit', 'commission_amount')


# ─── TECHNICIAN ─────────────────────────────────────────────────────────────────

@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'specialization', 'default_commission_rate', 'status')
    list_filter = ('status',)
    search_fields = ('name', 'phone', 'specialization')
    list_editable = ('status', 'default_commission_rate')


# ─── REPAIR JOB ─────────────────────────────────────────────────────────────────

@admin.register(RepairJob)
class RepairJobAdmin(admin.ModelAdmin):
    list_display = ('job_number', 'customer', 'device_info', 'status', 'current_stage', 'priority', 'assigned_technician', 'received_date')
    list_filter = ('status', 'priority', 'received_date', 'assigned_technician')
    search_fields = ('job_number', 'customer__name', 'customer__phone', 'device__brand', 'device__model', 'device__imei')
    readonly_fields = ('received_date', 'created_at', 'updated_at', 'job_number')
    autocomplete_fields = ['customer', 'device', 'assigned_technician']
    inlines = [DiagnosisInline, RepairEstimateInline, RepairPartInline, QualityCheckInline, WarrantyInline, CommissionInline, RepairStageHistoryInline, RepairStatusHistoryInline]
    ordering = ('-created_at',)
    actions = ['mark_as_ready_for_pickup', 'mark_as_delivered']
    list_per_page = 30

    @admin.display(description='Device')
    def device_info(self, obj):
        return f"{obj.device.brand} {obj.device.model}" if obj.device else "—"

    @admin.action(description="✅ Mark selected jobs as Ready for Pickup")
    def mark_as_ready_for_pickup(self, request, queryset):
        updated = queryset.update(status='READY_FOR_PICKUP')
        self.message_user(request, f"{updated} repair jobs updated to Ready for Pickup.", messages.SUCCESS)

    @admin.action(description="📦 Mark selected jobs as Delivered")
    def mark_as_delivered(self, request, queryset):
        updated = queryset.update(status='DELIVERED')
        self.message_user(request, f"{updated} repair jobs updated to Delivered.", messages.SUCCESS)


# ─── DIAGNOSIS ──────────────────────────────────────────────────────────────────

@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):
    list_display = ('repair_job', 'technician_diagnosis', 'recommended_repair', 'created_at', 'updated_at')
    search_fields = ('repair_job__job_number', 'technician_diagnosis', 'recommended_repair')
    ordering = ('-updated_at',)


# ─── REPAIR ESTIMATE ────────────────────────────────────────────────────────────

@admin.register(RepairEstimate)
class RepairEstimateAdmin(admin.ModelAdmin):
    list_display = ('repair_job', 'estimated_cost', 'status', 'rejection_reason', 'created_at', 'updated_at')
    list_filter = ('status', 'updated_at')
    search_fields = ('repair_job__job_number', 'repair_job__customer__name')
    list_editable = ('estimated_cost', 'status')
    ordering = ('-updated_at',)


# ─── INITIAL INSPECTION ─────────────────────────────────────────────────────────

@admin.register(InitialInspectionRecord)
class InitialInspectionRecordAdmin(admin.ModelAdmin):
    list_display = ('repair_job', 'power_on', 'display_condition', 'touch_working', 'body_condition', 'water_damage_signs', 'inspector', 'created_at')
    list_filter = ('power_on', 'touch_working', 'water_damage_signs', 'created_at')
    search_fields = ('repair_job__job_number', 'repair_job__customer__name')
    ordering = ('-created_at',)


# ─── QUALITY CHECK ──────────────────────────────────────────────────────────────

@admin.register(QualityCheckRecord)
class QualityCheckRecordAdmin(admin.ModelAdmin):
    list_display = ('repair_job', 'is_passed', 'display_ok', 'touch_ok', 'speaker_mic_ok', 'camera_ok', 'charging_ok', 'inspector', 'created_at')
    list_filter = ('is_passed', 'created_at')
    search_fields = ('repair_job__job_number', 'repair_job__customer__name')
    ordering = ('-created_at',)


# ─── TECHNICIAN COMMISSION ──────────────────────────────────────────────────────

@admin.register(TechnicianCommissionRecord)
class TechnicianCommissionRecordAdmin(admin.ModelAdmin):
    list_display = ('repair_job', 'technician', 'commission_type', 'commission_rate', 'gross_profit', 'commission_amount', 'is_paid', 'created_at')
    list_filter = ('is_paid', 'commission_type', 'created_at')
    search_fields = ('repair_job__job_number', 'technician__name')
    list_editable = ('is_paid',)
    readonly_fields = ('gross_profit', 'commission_amount', 'total_job_revenue', 'total_parts_cost')
    ordering = ('-created_at',)


# ─── WARRANTY RECORD ────────────────────────────────────────────────────────────

@admin.register(WarrantyRecord)
class WarrantyRecordAdmin(admin.ModelAdmin):
    list_display = ('repair_job', 'warranty_days', 'start_date', 'end_date', 'is_active', 'created_by', 'created_at')
    list_filter = ('is_active', 'start_date')
    search_fields = ('repair_job__job_number', 'repair_job__customer__name')
    list_editable = ('is_active',)
    ordering = ('-created_at',)


# ─── REPAIR STAGE HISTORY ───────────────────────────────────────────────────────

@admin.register(RepairStageHistory)
class RepairStageHistoryAdmin(admin.ModelAdmin):
    list_display = ('repair_job', 'stage_code', 'stage_name', 'status', 'created_by', 'created_at')
    list_filter = ('stage_code', 'status', 'created_at')
    search_fields = ('repair_job__job_number', 'stage_code', 'stage_name')
    readonly_fields = ('repair_job', 'stage_code', 'stage_name', 'status', 'data_snapshot', 'note', 'created_by', 'created_at')
    ordering = ('-created_at',)


# ─── REPAIR STATUS HISTORY ──────────────────────────────────────────────────────

@admin.register(RepairStatusHistory)
class RepairStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('repair_job', 'old_status', 'new_status', 'changed_by', 'timestamp')
    list_filter = ('new_status', 'timestamp')
    search_fields = ('repair_job__job_number', 'repair_job__customer__name')
    readonly_fields = ('repair_job', 'old_status', 'new_status', 'changed_by', 'timestamp', 'note')
    ordering = ('-timestamp',)
