from django.db import models
from django.contrib.auth.models import User
from customers.models import Customer, Device

class Technician(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='technician_profile')
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    specialization = models.CharField(max_length=255, blank=True, null=True)
    default_commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.00) # Default 10%
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    def __str__(self):
        return self.name

class RepairJob(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    
    STATUS_CHOICES = [
        ('RECEIVED', '1. Received (Mobile Shop par jama ho gaya)'),
        ('DEVICE_INTAKE', '2. Device Intake'),
        ('INITIAL_INSPECTION', '3. Initial Inspection'),
        ('DIAGNOSING', '4. Diagnosis (Technician check kar raha hai)'),
        ('ESTIMATE', '5. Repair Estimate'),
        ('WAITING_APPROVAL', '6. Waiting for Approval'),
        ('APPROVED', '7. Approved (Customer ne ijazat de di)'),
        ('TECHNICIAN_ASSIGNMENT', '8. Technician Assignment'),
        ('PARTS_ISSUE', '9. Parts Reservation / Issue'),
        ('REPAIRING', '10. Repair Work'),
        ('QUALITY_CHECK', '11. Quality Check'),
        ('READY_FOR_PICKUP', '12. Ready for Delivery'),
        ('FINAL_INVOICE', '13. Final Invoice'),
        ('PAYMENT', '14. Payment'),
        ('DELIVERED', '15. Delivered'),
        ('COMMISSION_CALCULATION', '16. Commission Calculation'),
        ('WARRANTY', '17. Warranty Active'),
        ('CANCELLED', 'Cancelled / Unrepairable'),
        ('UNREPAIRABLE', 'Unrepairable'),
        ('RETURNED', 'Returned'),
    ]

    LIFECYCLE_STAGES = [
        ('CUSTOMER', '1. Customer & Device Intake'),
        ('INITIAL_INSPECTION', '2. Initial Inspection'),
        ('DIAGNOSIS', '3. Diagnosis & Estimate'),
        ('CUSTOMER_APPROVAL', '4. Customer Approval'),
        ('PARTS_ISSUE', '5. Parts Reservation / Issue'),
        ('QUALITY_CHECK', '6. Quality Check'),
        ('FINAL_INVOICE', '7. Final Invoice & Notification'),
        ('PAYMENT', '8. Payment & Delivery'),
        ('COMMISSION_CALCULATION', '9. Commission Calculation'),
        ('WARRANTY', '10. Warranty'),
        # Legacy mappings for backward compatibility
        ('READY_FOR_DELIVERY', 'Legacy: Ready for Delivery'),
        ('REPAIR_JOB', 'Legacy: Repair Job'),
        ('TECHNICIAN_ASSIGNMENT', 'Legacy: Technician Assignment'),
        ('REPAIR_WORK', 'Legacy: Repair Work'),
        ('DELIVERY', 'Legacy: Delivery'),
        ('DEVICE_INTAKE', 'Legacy: Device Intake'),
        ('ESTIMATE', 'Legacy: Estimate'),
    ]

    job_number = models.CharField(max_length=50, unique=True, db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='repair_jobs')
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='repair_jobs')
    complaint = models.TextField()
    physical_condition = models.TextField(blank=True, null=True)
    accessories = models.TextField(blank=True, null=True)
    received_date = models.DateTimeField(auto_now_add=True, db_index=True)
    expected_delivery_date = models.DateTimeField(blank=True, null=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium', db_index=True)
    assigned_technician = models.ForeignKey(Technician, on_delete=models.CASCADE, null=True, blank=True, related_name='repair_jobs')
    referred_by_technician = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name='referred_jobs')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_repair_jobs')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='RECEIVED', db_index=True)
    current_stage = models.CharField(max_length=50, default='CUSTOMER', db_index=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.job_number} - {self.device.brand} {self.device.model}"

class RepairStatusHistory(models.Model):
    repair_job = models.ForeignKey(RepairJob, on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=30, blank=True, null=True)
    new_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.repair_job.job_number}: {self.old_status} -> {self.new_status}"

class RepairStageHistory(models.Model):
    repair_job = models.ForeignKey(RepairJob, on_delete=models.CASCADE, related_name='stage_histories')
    stage_code = models.CharField(max_length=50, db_index=True)
    stage_name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default='COMPLETED') # e.g., COMPLETED, IN_PROGRESS, SKIPPED, REJECTED
    data_snapshot = models.JSONField(default=dict, blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.repair_job.job_number} - Stage {self.stage_code} ({self.status}) at {self.created_at.strftime('%Y-%m-%d %H:%M')}"

class InitialInspectionRecord(models.Model):
    repair_job = models.ForeignKey(RepairJob, on_delete=models.CASCADE, related_name='inspection_records')
    power_on = models.BooleanField(default=True)
    display_condition = models.CharField(max_length=100, default='Good')
    touch_working = models.BooleanField(default=True)
    body_condition = models.CharField(max_length=100, default='Minor Scratches')
    camera_working = models.BooleanField(default=True)
    audio_working = models.BooleanField(default=True)
    charging_working = models.BooleanField(default=True)
    wifi_working = models.BooleanField(default=True)
    face_id_fingerprint = models.BooleanField(default=True)
    water_damage_signs = models.BooleanField(default=False)
    inspection_notes = models.TextField(blank=True, null=True)
    inspector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Inspection for {self.repair_job.job_number}"

class Diagnosis(models.Model):
    repair_job = models.OneToOneField(RepairJob, on_delete=models.CASCADE, related_name='diagnosis')
    technician_diagnosis = models.TextField()
    recommended_repair = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Diagnosis for {self.repair_job.job_number}"

from decimal import Decimal

class RepairEstimate(models.Model):
    ESTIMATE_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    repair_job = models.ForeignKey(RepairJob, on_delete=models.CASCADE, related_name='estimates')
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=ESTIMATE_STATUS, default='pending')
    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_estimate(self):
        return self.estimated_cost

    @property
    def estimated_labor_cost(self):
        return self.estimated_cost

    @property
    def estimated_parts_cost(self):
        return Decimal('0.00')

    def __str__(self):
        return f"Estimate Rs. {self.estimated_cost} for {self.repair_job.job_number} - {self.status}"

class QualityCheckRecord(models.Model):
    repair_job = models.ForeignKey(RepairJob, on_delete=models.CASCADE, related_name='quality_checks')
    display_ok = models.BooleanField(default=True)
    touch_ok = models.BooleanField(default=True)
    speaker_mic_ok = models.BooleanField(default=True)
    camera_ok = models.BooleanField(default=True)
    charging_ok = models.BooleanField(default=True)
    wifi_cellular_ok = models.BooleanField(default=True)
    buttons_ok = models.BooleanField(default=True)
    physical_clean_ok = models.BooleanField(default=True)
    is_passed = models.BooleanField(default=True)
    inspector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    qc_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"QC ({'PASS' if self.is_passed else 'FAIL'}) for {self.repair_job.job_number}"

class TechnicianCommissionRecord(models.Model):
    COMMISSION_TYPES = [
        ('percentage', 'Percentage (%)'),
        ('fixed', 'Fixed Amount'),
    ]
    repair_job = models.ForeignKey(RepairJob, on_delete=models.CASCADE, related_name='commissions')
    technician = models.ForeignKey(Technician, on_delete=models.CASCADE, related_name='commissions')
    commission_type = models.CharField(max_length=20, choices=COMMISSION_TYPES, default='percentage')
    commission_rate = models.DecimalField(max_digits=12, decimal_places=2, default=10.00)
    total_job_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_parts_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    gross_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_paid = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    calculated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Commission Rs. {self.commission_amount} for {self.technician.name} ({self.repair_job.job_number})"

class WarrantyRecord(models.Model):
    repair_job = models.ForeignKey(RepairJob, on_delete=models.CASCADE, related_name='warranties')
    warranty_days = models.IntegerField(default=30)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    terms_conditions = models.TextField(blank=True, null=True, default="Warranty covers original repair work and parts replaced. Physical damage or water exposure voids warranty.")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Warranty {self.warranty_days} Days for {self.repair_job.job_number}"

