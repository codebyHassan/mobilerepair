from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, F
from django.utils import timezone
from django.urls import reverse
from .models import (
    Technician, RepairJob, RepairStatusHistory, Diagnosis, RepairEstimate,
    RepairStageHistory, InitialInspectionRecord, QualityCheckRecord,
    TechnicianCommissionRecord, WarrantyRecord
)
from .forms import TechnicianForm, RepairJobForm, DiagnosisForm, RepairEstimateForm
from customers.models import Customer, Device
from billing.models import Invoice, Payment
from inventory.models import Part, RepairPart, InventoryTransaction, Supplier
from core.models import log_audit
from .permissions import RolePermission, shop_admin_required, technician_or_admin_required

def generate_job_number():
    from core.models import ShopSetting
    settings = ShopSetting.get_settings()
    year = timezone.localtime(timezone.now()).year
    prefix = settings.job_prefix
    
    count = RepairJob.objects.filter(received_date__year=year).count()
    seq = count + 1
    
    job_num = f"{prefix}-{year}-{seq:05d}"
    while RepairJob.objects.filter(job_number=job_num).exists():
        seq += 1
        job_num = f"{prefix}-{year}-{seq:05d}"
        
    return job_num

def recalculate_repair_bill(job):
    from decimal import Decimal
    parts_total = job.parts_used.annotate(
        total_part_price=F('customer_price') * F('quantity')
    ).aggregate(Sum('total_part_price'))['total_part_price__sum'] or Decimal('0.00')
    parts_total = Decimal(str(parts_total))
    
    estimate = job.estimates.order_by('-updated_at').first()
    labor = Decimal(str(estimate.estimated_labor_cost)) if estimate else Decimal('0.00')
    
    if hasattr(job, 'invoice'):
        invoice = job.invoice
        invoice.subtotal = parts_total + labor
        invoice.save()

def get_scoped_repair_jobs(request):
    perm = RolePermission(request.user)
    qs = RepairJob.objects.select_related('customer', 'device', 'assigned_technician', 'referred_by_technician', 'invoice').all().order_by('-received_date')
    if perm.can_view_all_repairs:
        return qs
    if perm.is_technician:
        tech = request.user.technician_profile
        return qs.filter(
            Q(assigned_technician=tech) |
            Q(referred_by_technician=tech) |
            Q(created_by=request.user)
        ).distinct()
    return qs.filter(created_by=request.user)

@login_required
def repair_list(request):
    status_filter = request.GET.get('status', '')
    query = request.GET.get('q', '')
    
    jobs_qs = get_scoped_repair_jobs(request)
    
    if status_filter:
        jobs_qs = jobs_qs.filter(status=status_filter)
        
    if query:
        jobs_qs = jobs_qs.filter(
            Q(job_number__icontains=query) |
            Q(customer__name__icontains=query) |
            Q(customer__phone__icontains=query) |
            Q(device__imei__icontains=query) |
            Q(device__model__icontains=query)
        ).distinct()
        
    statuses = RepairJob.STATUS_CHOICES
    
    return render(request, 'repairs/repair_list.html', {
        'jobs': jobs_qs,
        'statuses': statuses,
        'current_status': status_filter,
        'query': query
    })

@login_required
def repair_intake(request):
    from django.db import transaction
    from core.utils import decode_id

    # Handle Form Submission (POST) - Zero DB writes occur until user explicitly submits!
    if request.method == 'POST':
        customer_mode = request.POST.get('customer_mode')  # 'existing' or 'new'
        device_mode = request.POST.get('device_mode')      # 'existing' or 'new'
        
        try:
            with transaction.atomic():
                # 1. Resolve Customer
                if customer_mode == 'existing':
                    customer_id_raw = request.POST.get('customer_id')
                    customer_id = decode_id(customer_id_raw)
                    if not customer_id:
                        raise ValueError("Please select a customer from the search results.")
                    customer = get_object_or_404(Customer, pk=customer_id)
                elif customer_mode == 'new':
                    customer_name = request.POST.get('customer_name', '').strip()
                    customer_phone = request.POST.get('customer_phone', '').strip()
                    customer_whatsapp = request.POST.get('customer_whatsapp', '').strip()
                    customer_email = request.POST.get('customer_email', '').strip()
                    customer_address = request.POST.get('customer_address', '').strip()
                    customer_notes = request.POST.get('customer_notes', '').strip()
                    
                    if not customer_name:
                        raise ValueError("New Customer Name is required.")
                    if not customer_phone:
                        raise ValueError("New Customer Phone number is required.")
                    
                    # Create customer
                    customer = Customer.objects.create(
                        name=customer_name,
                        phone=customer_phone,
                        whatsapp=customer_whatsapp or customer_phone,
                        email=customer_email or None,
                        address=customer_address or None,
                        notes=customer_notes or None
                    )
                    log_audit(request, 'CREATE', 'Customer', customer.name, details=f"Registered customer {customer.name} (Phone: {customer.phone}) during quick intake", object_id=customer.id)
                else:
                    raise ValueError("Please select or register a customer.")
                
                # 2. Resolve Device
                if device_mode == 'existing':
                    device_id_raw = request.POST.get('device_id')
                    device_id = decode_id(device_id_raw)
                    if not device_id:
                        raise ValueError("Please select a device from the customer's device list.")
                    device = get_object_or_404(Device, pk=device_id)
                elif device_mode == 'new':
                    device_brand = request.POST.get('device_brand', '').strip()
                    device_model = request.POST.get('device_model', '').strip()
                    device_imei = request.POST.get('device_imei', '').strip()
                    device_color = request.POST.get('device_color', '').strip()
                    device_storage = request.POST.get('device_storage', '').strip()
                    device_password = request.POST.get('device_password', '').strip()
                    device_physical_condition = request.POST.get('device_physical_condition', '').strip()
                    device_accessories = request.POST.get('device_accessories_received', '').strip()
                    
                    if not device_brand or not device_model:
                        raise ValueError("Device Brand and Model are required for new device registration.")
                    
                    device = Device.objects.create(
                        customer=customer,
                        brand=device_brand,
                        model=device_model,
                        imei=device_imei or None,
                        color=device_color or None,
                        storage=device_storage or None,
                        device_password=device_password or None,
                        physical_condition=device_physical_condition or None,
                        accessories_received=device_accessories or None
                    )
                    log_audit(request, 'CREATE', 'Device', f"{device.brand} {device.model}", details=f"Registered device for customer {customer.name}", object_id=device.id)
                else:
                    raise ValueError("Please select or register a device.")
                
                # 3. Create Repair Job
                complaint = request.POST.get('complaint', '').strip()
                priority = request.POST.get('priority', 'medium')
                expected_delivery_str = request.POST.get('expected_delivery_date', '').strip()
                assigned_tech_raw = request.POST.get('assigned_technician', '').strip()
                physical_condition = request.POST.get('physical_condition', '').strip()
                accessories = request.POST.get('accessories', '').strip()
                notes = request.POST.get('notes', '').strip()
                
                if not complaint:
                    raise ValueError("Customer Complaint description is required.")
                    
                # Default physical condition & accessories to device details if empty
                if not physical_condition:
                    physical_condition = device.physical_condition or ""
                if not accessories:
                    accessories = device.accessories_received or ""
                    
                expected_delivery_date = None
                if expected_delivery_str:
                    try:
                        expected_delivery_date = timezone.datetime.fromisoformat(expected_delivery_str)
                        if timezone.is_naive(expected_delivery_date):
                            expected_delivery_date = timezone.make_aware(expected_delivery_date)
                    except ValueError:
                        pass
                
                assigned_technician = None
                if assigned_tech_raw:
                    assigned_tech_id = decode_id(assigned_tech_raw)
                    if assigned_tech_id:
                        assigned_technician = get_object_or_404(Technician, pk=assigned_tech_id)

                referred_tech_raw = request.POST.get('referred_by_technician', '').strip()
                referred_by_technician = None
                if referred_tech_raw:
                    ref_id = decode_id(referred_tech_raw) or (int(referred_tech_raw) if referred_tech_raw.isdigit() else None)
                    if ref_id:
                        referred_by_technician = Technician.objects.filter(pk=ref_id).first()
                if not referred_by_technician and hasattr(request.user, 'technician_profile'):
                    referred_by_technician = request.user.technician_profile
                
                job = RepairJob.objects.create(
                    customer=customer,
                    device=device,
                    job_number=generate_job_number(),
                    complaint=complaint,
                    physical_condition=physical_condition,
                    accessories=accessories,
                    expected_delivery_date=expected_delivery_date,
                    priority=priority,
                    assigned_technician=assigned_technician,
                    referred_by_technician=referred_by_technician,
                    created_by=request.user,
                    status='RECEIVED',
                    notes=notes
                )
                
                # Log intake in status history
                RepairStatusHistory.objects.create(
                    repair_job=job,
                    old_status=None,
                    new_status='RECEIVED',
                    changed_by=request.user,
                    note="Job intake registered via Unified Intake Wizard"
                )
                
                # Initialize empty diagnosis and estimate
                Diagnosis.objects.create(repair_job=job, technician_diagnosis='', recommended_repair='')
                RepairEstimate.objects.create(repair_job=job)
                
                # Auto-generate linked invoice
                from core.models import ShopSetting
                inv_settings = ShopSetting.get_settings()
                year = timezone.localtime(timezone.now()).year
                inv_count = Invoice.objects.filter(created_at__year=year).count() + 1
                inv_num = f"{inv_settings.invoice_prefix}-{year}-{inv_count:05d}"
                while Invoice.objects.filter(invoice_number=inv_num).exists():
                    inv_count += 1
                    inv_num = f"{inv_settings.invoice_prefix}-{year}-{inv_count:05d}"
                    
                Invoice.objects.create(
                    invoice_number=inv_num,
                    repair_job=job,
                    subtotal=0.00,
                    discount=0.00
                )
                
                log_audit(request, 'CREATE', 'RepairJob', job.job_number, details=f"Registered repair job intake for {job.customer.name} (Device: {job.device.brand} {job.device.model}) via Unified Intake Wizard", object_id=job.id)
                messages.success(request, f"Repair Job {job.job_number} created successfully.")
                return redirect('repair_detail', pk=job.id)
                
        except Exception as e:
            messages.error(request, f"⚠️ Error registering intake: {str(e)}")
            return redirect('repair_intake')
            
    # GET method
    technicians = Technician.objects.filter(status='active').order_by('name')
    priorities = RepairJob.PRIORITY_CHOICES
    
    return render(request, 'repairs/repair_intake.html', {
        'technicians': technicians,
        'priorities': priorities,
        'title': 'Quick Repair Intake Wizard'
    })


@login_required
def repair_create(request):
    customer_id = request.GET.get('customer_id')
    device_id = request.GET.get('device_id')
    
    customer = None
    device = None
    
    if customer_id:
        customer = get_object_or_404(Customer, pk=customer_id)
    if device_id:
        device = get_object_or_404(Device, pk=device_id)
        
    if not customer or not device:
        messages.error(request, "Please select a customer and device first.")
        return redirect('repair_intake')
        
    if request.method == 'POST':
        form = RepairJobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.customer = customer
            job.device = device
            job.job_number = generate_job_number()
            job.save()
            
            # Log intake in status history
            RepairStatusHistory.objects.create(
                repair_job=job,
                old_status=None,
                new_status=job.status,
                changed_by=request.user,
                note="Job intake registered"
            )
            
            # Initialize empty diagnosis and estimate
            Diagnosis.objects.create(repair_job=job, technician_diagnosis='', recommended_repair='')
            RepairEstimate.objects.create(repair_job=job)
            
            # Auto-generate linked invoice
            from core.models import ShopSetting
            inv_settings = ShopSetting.get_settings()
            year = timezone.localtime(timezone.now()).year
            inv_count = Invoice.objects.filter(created_at__year=year).count() + 1
            inv_num = f"{inv_settings.invoice_prefix}-{year}-{inv_count:05d}"
            while Invoice.objects.filter(invoice_number=inv_num).exists():
                inv_count += 1
                inv_num = f"{inv_settings.invoice_prefix}-{year}-{inv_count:05d}"
                
            Invoice.objects.create(
                invoice_number=inv_num,
                repair_job=job,
                subtotal=0.00,
                discount=0.00
            )
            
            log_audit(request, 'CREATE', 'RepairJob', job.job_number, details=f"Registered repair job intake for {job.customer.name} (Device: {job.device.brand} {job.device.model})", object_id=job.id)
            messages.success(request, f"Repair Job {job.job_number} created successfully.")
            return redirect('repair_detail', pk=job.id)
    else:
        form = RepairJobForm()
        
    return render(request, 'repairs/repair_form.html', {
        'form': form,
        'customer': customer,
        'device': device,
        'title': 'Create New Repair Job'
    })

LIFECYCLE_STAGES_CONFIG = [
    {'code': 'CUSTOMER', 'number': 1, 'title': 'Customer & Device', 'subtitle': 'Customer & Device Intake', 'icon': 'bi-person-vcard'},
    {'code': 'INITIAL_INSPECTION', 'number': 2, 'title': 'Initial Inspection', 'subtitle': 'Physical & Functional Check', 'icon': 'bi-clipboard-check'},
    {'code': 'DIAGNOSIS', 'number': 3, 'title': 'Diagnosis & Estimate', 'subtitle': 'Fault Assessment, Tech & Costing', 'icon': 'bi-calculator-fill'},
    {'code': 'CUSTOMER_APPROVAL', 'number': 4, 'title': 'Customer Approval', 'subtitle': 'Estimate Confirmation', 'icon': 'bi-hand-thumbs-up'},
    {'code': 'PARTS_ISSUE', 'number': 5, 'title': 'Parts Reservation', 'subtitle': 'Inventory Parts Allocation', 'icon': 'bi-cpu'},
    {'code': 'QUALITY_CHECK', 'number': 6, 'title': 'Quality Check', 'subtitle': 'QC Testing & Pass/Fail', 'icon': 'bi-shield-check'},
    {'code': 'FINAL_INVOICE', 'number': 7, 'title': 'Final Invoice & Slip', 'subtitle': 'Billing, Discounts & WhatsApp Bill', 'icon': 'bi-receipt'},
    {'code': 'PAYMENT', 'number': 8, 'title': 'Payment & Delivery', 'subtitle': 'Payment Collection & Handoff', 'icon': 'bi-credit-card'},
    {'code': 'WARRANTY', 'number': 9, 'title': 'Warranty', 'subtitle': 'Warranty Policy & Terms', 'icon': 'bi-patch-check'},
    {'code': 'COMMISSION_CALCULATION', 'number': 10, 'title': 'Commission', 'subtitle': 'Tech Commission (Last Step)', 'icon': 'bi-cash-coin'},
]

LEGACY_STAGE_REMAP = {
    'DEVICE_INTAKE': 'CUSTOMER',
    'ESTIMATE': 'DIAGNOSIS',
    'REPAIR_JOB': 'CUSTOMER_APPROVAL',
    'TECHNICIAN_ASSIGNMENT': 'DIAGNOSIS',
    'REPAIR_WORK': 'PARTS_ISSUE',
    'READY_FOR_DELIVERY': 'FINAL_INVOICE',
    'DELIVERY': 'PAYMENT',
}

@login_required
def repair_detail(request, pk):
    job = get_object_or_404(RepairJob, pk=pk)
    stage = job.current_stage or 'CUSTOMER'
    stage = LEGACY_STAGE_REMAP.get(stage, stage)
    return redirect('repair_lifecycle_stage', pk=job.id, stage_code=stage)

@login_required
def repair_lifecycle(request, pk, stage_code=None):
    from decimal import Decimal
    from django.db import transaction
    from core.utils import decode_id

    job = get_object_or_404(
        RepairJob.objects.select_related('customer', 'device', 'assigned_technician', 'invoice'),
        pk=pk
    )

    perm = RolePermission(request.user)
    if not perm.can_access_job(job):
        messages.error(request, "⛔ Access Restricted: You can only access repair jobs assigned to or brought in by you.")
        return redirect('repair_list')

    # Remap legacy stage codes for backwards compatibility
    if stage_code:
        stage_code = LEGACY_STAGE_REMAP.get(stage_code, stage_code)

    if job.current_stage:
        job.current_stage = LEGACY_STAGE_REMAP.get(job.current_stage, job.current_stage)

    # Ensure invoice exists
    if not hasattr(job, 'invoice'):
        from core.models import ShopSetting
        inv_settings = ShopSetting.get_settings()
        year = timezone.localtime(timezone.now()).year
        inv_count = Invoice.objects.filter(created_at__year=year).count() + 1
        inv_num = f"{inv_settings.invoice_prefix}-{year}-{inv_count:05d}"
        while Invoice.objects.filter(invoice_number=inv_num).exists():
            inv_count += 1
            inv_num = f"{inv_settings.invoice_prefix}-{year}-{inv_count:05d}"
            
        Invoice.objects.create(
            invoice_number=inv_num,
            repair_job=job,
            subtotal=0.00,
            discount=0.00
        )
        job.refresh_from_db()

    # Stage codes list
    stage_codes = [s['code'] for s in LIFECYCLE_STAGES_CONFIG]

    # Completed stage codes set (also normalize legacy stage completions)
    raw_completed_stages = set(job.stage_histories.filter(status='COMPLETED').values_list('stage_code', flat=True))
    completed_stages_set = set()
    for sc in raw_completed_stages:
        completed_stages_set.add(LEGACY_STAGE_REMAP.get(sc, sc))

    current_job_stage = LEGACY_STAGE_REMAP.get(job.current_stage, job.current_stage) or 'CUSTOMER'
    if current_job_stage not in stage_codes:
        current_job_stage = 'CUSTOMER'

    # Current job stage rank (1-based index)
    current_job_stage_idx = 1
    for s in LIFECYCLE_STAGES_CONFIG:
        if s['code'] == current_job_stage:
            current_job_stage_idx = s['number']
            break

    # Active requested stage selection
    if not stage_code or stage_code not in stage_codes:
        stage_code = current_job_stage
    stage_code = LEGACY_STAGE_REMAP.get(stage_code, stage_code)

    # Requested stage rank (1-based index)
    requested_stage_idx = 1
    for s in LIFECYCLE_STAGES_CONFIG:
        if s['code'] == stage_code:
            requested_stage_idx = s['number']
            break

    # Customer Approval Rejection check
    est_record = job.estimates.order_by('-updated_at').first()
    is_approval_rejected = bool(est_record and est_record.status == 'rejected')

    # STRICT SEQUENTIAL STEP-BY-STEP ENFORCEMENT & REJECTION HALT (Technician-only; Superadmin has full bypass):
    if not perm.is_admin:
        # If Customer Approval is rejected, any stage beyond Stage 4 (CUSTOMER_APPROVAL) is completely blocked for technicians!
        if is_approval_rejected and requested_stage_idx > 4:
            messages.error(
                request,
                "⛔ Lifecycle is HALTED because Customer Approval was REJECTED! Please approve the estimate to resume."
            )
            return redirect('repair_lifecycle_stage', pk=job.id, stage_code='CUSTOMER_APPROVAL')

        # A stage is accessible ONLY if:
        # 1. It is already completed (in completed_stages_set)
        # 2. OR it is the current active stage (code == current_job_stage)
        # If a technician tries to jump ahead into a future uncompleted stage, redirect them back to current_job_stage!
        if requested_stage_idx > current_job_stage_idx and stage_code not in completed_stages_set:
            messages.warning(
                request,
                f"🔒 Stage #{requested_stage_idx} is locked! Please submit and complete Stage #{current_job_stage_idx} ({current_job_stage}) first before proceeding."
            )
            return redirect('repair_lifecycle_stage', pk=job.id, stage_code=current_job_stage)

    current_stage_idx = requested_stage_idx

    # Completed Stage Locking Check:
    # Superadmin / Admin can ALWAYS edit any form without being locked.
    # Technicians are locked out of previously completed stages unless explicitly unlocked.
    admin_unlock = (request.GET.get('unlock') == 'true' or request.POST.get('unlock') == 'true') and perm.is_admin
    if perm.is_admin:
        is_stage_locked = False
    else:
        is_stage_locked = (stage_code in completed_stages_set and stage_code != current_job_stage) and not admin_unlock

    # Build Stepper status array
    stages_flow = []
    for s in LIFECYCLE_STAGES_CONFIG:
        code = s['code']
        num = s['number']
        is_completed = (code in completed_stages_set)
        is_current_active = (code == current_job_stage)
        
        if perm.is_admin:
            # Superadmin has full unrestricted navigation to all stages
            is_accessible = True
            if code == stage_code:
                status = 'active'
                icon = s['icon']
            elif is_approval_rejected and code == 'CUSTOMER_APPROVAL':
                status = 'rejected'
                icon = 'bi-x-circle-fill'
            elif is_completed:
                status = 'completed'
                icon = s['icon']
            elif is_current_active:
                status = 'unlocked'
                icon = s['icon']
            else:
                status = 'unlocked'
                icon = s['icon']
        else:
            # Regular technician constraints
            if is_approval_rejected and num > 4:
                status = 'halted'
                is_accessible = False
                icon = 'bi-x'
            elif is_approval_rejected and code == 'CUSTOMER_APPROVAL':
                status = 'rejected'
                is_accessible = True
                icon = 'bi-x-circle-fill'
            elif code == stage_code:
                status = 'active'
                is_accessible = True
                icon = s['icon']
            elif is_completed:
                status = 'completed'
                is_accessible = True
                icon = s['icon']
            elif is_current_active:
                status = 'unlocked'
                is_accessible = True
                icon = s['icon']
            else:
                status = 'pending'
                is_accessible = False
                icon = s['icon']
            
        stages_flow.append({
            'code': code,
            'number': num,
            'title': s['title'],
            'subtitle': s['subtitle'],
            'icon': icon,
            'status': status,
            'is_accessible': is_accessible,
            'is_current': (code == stage_code)
        })

    # Previous and Next stage codes
    prev_stage = stage_codes[current_stage_idx - 2] if current_stage_idx > 1 else None
    next_stage = stage_codes[current_stage_idx] if current_stage_idx < len(stage_codes) and (perm.is_admin or not (is_approval_rejected and stage_code == 'CUSTOMER_APPROVAL')) else None

    # Handle POST form actions
    if request.method == 'POST':
        action = request.POST.get('action', 'save_stage')
        target_stage = request.POST.get('stage_code', stage_code)
        target_stage = LEGACY_STAGE_REMAP.get(target_stage, target_stage)

        note = request.POST.get('stage_note', '')
        snapshot_data = {}

        if is_stage_locked and not perm.is_admin:
            messages.error(request, f"🔒 Stage '{target_stage}' is submitted & locked! Admin unlock required to edit.")
            return redirect('repair_lifecycle_stage', pk=job.id, stage_code=target_stage)

        try:
            with transaction.atomic():
                # 1. CUSTOMER & DEVICE INTAKE STAGE (COMBINED)
                if target_stage in ['CUSTOMER', 'DEVICE_INTAKE']:
                    customer_mode = request.POST.get('customer_mode', 'current')
                    device_mode = request.POST.get('device_mode', 'current')

                    # Customer handling
                    prev_cust = job.customer
                    is_placeholder_cust = (prev_cust and (prev_cust.name == "New Customer" or prev_cust.phone == "0000000000"))

                    if customer_mode == 'existing':
                        cust_id_raw = request.POST.get('customer_id')
                        if cust_id_raw:
                            try:
                                c_id = int(cust_id_raw) if str(cust_id_raw).isdigit() else decode_id(cust_id_raw)
                                cust = Customer.objects.get(pk=c_id)
                                job.customer = cust
                                # Clean up unused placeholder customer
                                if is_placeholder_cust and prev_cust != cust and prev_cust.repair_jobs.exclude(pk=job.id).count() == 0:
                                    prev_cust.delete()
                            except (Customer.DoesNotExist, ValueError):
                                cust = prev_cust
                        else:
                            cust = prev_cust
                    elif customer_mode == 'new':
                        c_name = request.POST.get('name', '').strip() or "New Customer"
                        c_phone = request.POST.get('phone', '').strip() or "0000000000"
                        c_wa = request.POST.get('whatsapp', '').strip() or c_phone
                        c_email = request.POST.get('email', '').strip() or None
                        c_addr = request.POST.get('address', '').strip() or None
                        c_notes = request.POST.get('notes', '').strip() or None

                        cust = Customer.objects.create(
                            name=c_name,
                            phone=c_phone,
                            whatsapp=c_wa,
                            email=c_email,
                            address=c_addr,
                            notes=c_notes
                        )
                        log_audit(request, 'CREATE', 'Customer', cust.name, details=f"Registered customer via Lifecycle (Phone: {cust.phone})", object_id=cust.id)
                        if is_placeholder_cust and prev_cust and prev_cust.repair_jobs.exclude(pk=job.id).count() == 0:
                            prev_cust.delete()
                        job.customer = cust
                    else:
                        # 'current' or 'edit': Update current customer in-place
                        c_name = request.POST.get('name', '').strip()
                        c_phone = request.POST.get('phone', '').strip()
                        c_wa = request.POST.get('whatsapp', '').strip()
                        c_email = request.POST.get('email', '').strip() or None
                        c_addr = request.POST.get('address', '').strip() or None
                        c_notes = request.POST.get('notes', '').strip() or None

                        if prev_cust:
                            cust = prev_cust
                            if c_name:
                                cust.name = c_name
                            if c_phone:
                                cust.phone = c_phone
                            if c_wa:
                                cust.whatsapp = c_wa
                            cust.email = c_email
                            cust.address = c_addr
                            cust.notes = c_notes
                            cust.save()
                        else:
                            cust = Customer.objects.create(
                                name=c_name or "New Customer",
                                phone=c_phone or "0000000000",
                                whatsapp=c_wa or c_phone or "0000000000",
                                email=c_email,
                                address=c_addr,
                                notes=c_notes
                            )
                        job.customer = cust

                    # Device handling
                    prev_dev = job.device
                    is_placeholder_dev = (prev_dev and (prev_dev.brand == "Generic" or prev_dev.model == "Unspecified Model"))

                    if device_mode == 'existing':
                        dev_id_raw = request.POST.get('device_id')
                        if dev_id_raw:
                            try:
                                d_id = int(dev_id_raw) if str(dev_id_raw).isdigit() else decode_id(dev_id_raw)
                                dev = Device.objects.get(pk=d_id)
                                job.device = dev
                                # Clean up unused placeholder device
                                if is_placeholder_dev and prev_dev != dev and prev_dev.repair_jobs.exclude(pk=job.id).count() == 0:
                                    prev_dev.delete()
                            except (Device.DoesNotExist, ValueError):
                                dev = prev_dev
                        else:
                            dev = prev_dev
                    elif device_mode == 'new':
                        d_brand = request.POST.get('brand', '').strip() or "Generic"
                        d_model = request.POST.get('model', '').strip() or "Unspecified Model"
                        d_imei = request.POST.get('imei', '').strip() or None
                        d_color = request.POST.get('color', '').strip() or None
                        d_storage = request.POST.get('storage', '').strip() or None
                        d_pass = request.POST.get('device_password', '').strip() or None
                        d_phys = request.POST.get('physical_condition', '').strip() or None
                        d_acc = request.POST.get('accessories_received', '').strip() or None

                        dev = Device.objects.create(
                            customer=job.customer,
                            brand=d_brand,
                            model=d_model,
                            imei=d_imei,
                            color=d_color,
                            storage=d_storage,
                            device_password=d_pass,
                            physical_condition=d_phys,
                            accessories_received=d_acc
                        )
                        log_audit(request, 'CREATE', 'Device', f"{dev.brand} {dev.model}", details=f"Registered device via Lifecycle for {job.customer.name}", object_id=dev.id)
                        if is_placeholder_dev and prev_dev and prev_dev.repair_jobs.exclude(pk=job.id).count() == 0:
                            prev_dev.delete()
                        job.device = dev
                    else:
                        # 'current' or 'edit': Update current device in-place
                        d_brand = request.POST.get('brand', '').strip()
                        d_model = request.POST.get('model', '').strip()
                        d_imei = request.POST.get('imei', '').strip() or None
                        d_color = request.POST.get('color', '').strip() or None
                        d_storage = request.POST.get('storage', '').strip() or None
                        d_pass = request.POST.get('device_password', '').strip() or None
                        d_phys = request.POST.get('physical_condition', '').strip() or None
                        d_acc = request.POST.get('accessories_received', '').strip() or None

                        if prev_dev:
                            dev = prev_dev
                            dev.customer = job.customer
                            if d_brand:
                                dev.brand = d_brand
                            if d_model:
                                dev.model = d_model
                            dev.imei = d_imei
                            dev.color = d_color
                            dev.storage = d_storage
                            dev.device_password = d_pass
                            dev.physical_condition = d_phys
                            dev.accessories_received = d_acc
                            dev.save()
                        else:
                            dev = Device.objects.create(
                                customer=job.customer,
                                brand=d_brand or "Generic",
                                model=d_model or "Unspecified Model",
                                imei=d_imei,
                                color=d_color,
                                storage=d_storage,
                                device_password=d_pass,
                                physical_condition=d_phys,
                                accessories_received=d_acc
                            )
                        job.device = dev

                    job.complaint = request.POST.get('complaint', job.complaint).strip() or job.complaint
                    job.physical_condition = job.device.physical_condition
                    job.accessories = job.device.accessories_received
                    job.save()

                    snapshot_data = {
                        'customer': job.customer.name,
                        'phone': job.customer.phone,
                        'device': f"{job.device.brand} {job.device.model}",
                        'imei': job.device.imei,
                        'complaint': job.complaint
                    }
                    messages.success(request, "Customer and Device Intake details updated successfully.")

                # 2. INITIAL INSPECTION STAGE
                elif target_stage == 'INITIAL_INSPECTION':
                    insp, _ = InitialInspectionRecord.objects.get_or_create(repair_job=job)
                    insp.power_on = request.POST.get('power_on') in ['true', 'on', '1', True]
                    insp.display_condition = request.POST.get('display_condition', 'Good')
                    insp.touch_working = request.POST.get('touch_working') in ['true', 'on', '1', True]
                    insp.body_condition = request.POST.get('body_condition', 'Minor Scratches')
                    insp.camera_working = request.POST.get('camera_working') in ['true', 'on', '1', True]
                    insp.audio_working = request.POST.get('audio_working') in ['true', 'on', '1', True]
                    insp.charging_working = request.POST.get('charging_working') in ['true', 'on', '1', True]
                    insp.wifi_working = request.POST.get('wifi_working') in ['true', 'on', '1', True]
                    insp.face_id_fingerprint = request.POST.get('face_id_fingerprint') in ['true', 'on', '1', True]
                    insp.water_damage_signs = request.POST.get('water_damage_signs') in ['true', 'on', '1', True]
                    insp.inspection_notes = request.POST.get('inspection_notes', '').strip()
                    insp.inspector = request.user if request.user.is_authenticated else None
                    insp.save()

                    snapshot_data = {
                        'power_on': insp.power_on,
                        'display': insp.display_condition,
                        'touch': insp.touch_working,
                        'body': insp.body_condition,
                        'water_damage': insp.water_damage_signs,
                        'notes': insp.inspection_notes
                    }
                    messages.success(request, "Initial inspection record logged.")

                # 3. DIAGNOSIS & ESTIMATE STAGE
                elif target_stage in ['DIAGNOSIS', 'ESTIMATE', 'TECHNICIAN_ASSIGNMENT', 'REPAIR_JOB']:
                    diag, _ = Diagnosis.objects.get_or_create(repair_job=job)
                    diag.technician_diagnosis = request.POST.get('technician_diagnosis', '').strip()
                    diag.recommended_repair = request.POST.get('recommended_repair', '').strip()
                    diag.save()

                    est = job.estimates.order_by('-updated_at').first()
                    if not est:
                        est = RepairEstimate.objects.create(repair_job=job)

                    est_cost_raw = request.POST.get('estimated_cost', '').strip()
                    if not est_cost_raw:
                        raise ValueError("Estimated Cost is required and cannot be empty.")
                    try:
                        from decimal import InvalidOperation
                        est_cost_val = Decimal(est_cost_raw)
                        if est_cost_val < 0:
                            raise ValueError("Estimated Cost cannot be negative.")
                    except (InvalidOperation, ValueError) as e:
                        raise ValueError(f"Invalid Estimated Cost: {str(e)}")

                    est.estimated_cost = est_cost_val
                    est.save()

                    exp_date = request.POST.get('expected_delivery_date', '')
                    if exp_date:
                        try:
                            dt = timezone.datetime.fromisoformat(exp_date)
                            if timezone.is_naive(dt):
                                dt = timezone.make_aware(dt)
                            job.expected_delivery_date = dt
                            job.save()
                        except ValueError:
                            pass

                    recalculate_repair_bill(job)
                    snapshot_data = {
                        'diagnosis': diag.technician_diagnosis,
                        'recommended_repair': diag.recommended_repair,
                        'estimated_cost': str(est.estimated_cost),
                    }
                    messages.success(request, f"Diagnosis and Estimate (Rs. {est.estimated_cost:,.2f}) saved successfully.")

                # 4. CUSTOMER APPROVAL STAGE
                elif target_stage == 'CUSTOMER_APPROVAL':
                    est = job.estimates.order_by('-updated_at').first()
                    if not est:
                        est = RepairEstimate.objects.create(repair_job=job)
                    app_status = request.POST.get('approval_status', 'approved')
                    est.status = app_status
                    est.rejection_reason = request.POST.get('rejection_reason', '').strip() if app_status == 'rejected' else None
                    est.save()

                    if app_status == 'rejected':
                        job.status = 'CANCELLED'
                        job.current_stage = 'CUSTOMER_APPROVAL'
                        job.save()
                        snapshot_data = {'approval_status': 'rejected', 'rejection_reason': est.rejection_reason}
                        messages.warning(request, "⛔ Customer Approval REJECTED. Repair workflow is marked rejected.")
                        return redirect('repair_lifecycle_stage', pk=job.id, stage_code='CUSTOMER_APPROVAL')
                    elif app_status == 'approved':
                        job.status = 'APPROVED'
                        job.current_stage = 'PARTS_ISSUE'
                        job.save()
                        snapshot_data = {'approval_status': 'approved'}
                        messages.success(request, "✅ Customer Approved! Lifecycle advanced to Stage 5 (Parts Issue).")
                        return redirect('repair_lifecycle_stage', pk=job.id, stage_code='PARTS_ISSUE')
                    else:
                        job.current_stage = 'CUSTOMER_APPROVAL'
                        job.save()
                        snapshot_data = {'approval_status': 'pending'}
                        messages.info(request, "⏳ Customer Approval set to Pending. Waiting for customer confirmation.")
                        return redirect('repair_lifecycle_stage', pk=job.id, stage_code='CUSTOMER_APPROVAL')

                # 5. PARTS ISSUE STAGE (MULTIPLE PARTS, SUPPLIER UDHAR & STOCK MATRIX)
                elif target_stage in ['PARTS_ISSUE', 'REPAIR_WORK']:
                    part_action = request.POST.get('part_action', '')
                    
                    # 1. Remove / Return an issued part
                    if part_action == 'remove_part' or request.POST.get('remove_repair_part_id'):
                        rp_id = request.POST.get('remove_repair_part_id')
                        try:
                            rp = RepairPart.objects.get(pk=rp_id, repair_job=job)
                            p = rp.part
                            p.current_stock += rp.quantity
                            p.save()

                            InventoryTransaction.objects.create(
                                part=p,
                                transaction_type='return',
                                quantity=rp.quantity,
                                repair_job=job,
                                note=f"Returned from Repair Job {job.job_number}",
                                created_by=request.user if request.user.is_authenticated else None
                            )

                            p_name = p.name
                            rp.delete()
                            recalculate_repair_bill(job)
                            messages.success(request, f"Part '{p_name}' removed from job & returned to inventory stock.")
                        except RepairPart.DoesNotExist:
                            pass
                        return redirect('repair_lifecycle_stage', pk=job.id, stage_code='PARTS_ISSUE')

                    # 2. Add / Issue from existing inventory or new supplier
                    part_source_type = request.POST.get('part_source_type', 'existing_stock')
                    part_id = request.POST.get('part_id')
                    new_part_name = request.POST.get('new_part_name', '').strip()

                    if part_source_type == 'existing_stock' and part_id:
                        qty = int(request.POST.get('quantity', 1) or 1)
                        part_obj = get_object_or_404(Part, pk=part_id)
                        cust_price = Decimal(request.POST.get('customer_price', str(part_obj.selling_price)) or str(part_obj.selling_price))

                        RepairPart.objects.create(
                            repair_job=job,
                            part=part_obj,
                            quantity=qty,
                            purchase_cost=part_obj.purchase_cost,
                            customer_price=cust_price
                        )

                        part_obj.current_stock = max(0, part_obj.current_stock - qty)
                        part_obj.save()

                        InventoryTransaction.objects.create(
                            part=part_obj,
                            transaction_type='repair_use',
                            quantity=-qty,
                            repair_job=job,
                            note=f"Issued to Repair Job {job.job_number}",
                            created_by=request.user if request.user.is_authenticated else None
                        )

                        recalculate_repair_bill(job)
                        snapshot_data = {'part': part_obj.name, 'quantity': qty, 'customer_price': str(cust_price)}
                        messages.success(request, f"✅ Part '{part_obj.name}' x{qty} issued to repair job.")

                    elif part_source_type == 'new_supplier_part' and new_part_name:
                        supp_id = request.POST.get('supplier_id')
                        supplier_obj = Supplier.objects.filter(pk=supp_id).first() if supp_id else None
                        part_category = request.POST.get('new_part_category', 'Replacement Component').strip() or 'Replacement Component'
                        purchase_cost = Decimal(request.POST.get('purchase_cost', '0') or '0')
                        cust_price_raw = request.POST.get('supplier_customer_price') or request.POST.get('customer_price')
                        cust_price = Decimal(cust_price_raw or str(purchase_cost))
                        qty_raw = request.POST.get('supplier_qty') or request.POST.get('quantity') or 1
                        qty = int(qty_raw or 1)
                        is_credit = (request.POST.get('is_credit_purchase') in ['true', 'on', '1', True])

                        sku = f"PRT-{timezone.now().strftime('%y%m%d%H%M%S')}"
                        new_part = Part.objects.create(
                            name=new_part_name,
                            sku=sku,
                            category=part_category,
                            compatible_device=f"{job.device.brand} {job.device.model}",
                            purchase_cost=purchase_cost,
                            selling_price=cust_price,
                            current_stock=0,
                            supplier_fk=supplier_obj,
                            supplier=supplier_obj.name if supplier_obj else (request.POST.get('supplier_name_text') or None),
                            is_credit_purchase=is_credit,
                            notes=f"Auto-registered from Supplier & issued to #{job.job_number} (Udhar Khata: {is_credit})"
                        )

                        RepairPart.objects.create(
                            repair_job=job,
                            part=new_part,
                            quantity=qty,
                            purchase_cost=purchase_cost,
                            customer_price=cust_price
                        )

                        InventoryTransaction.objects.create(
                            part=new_part,
                            transaction_type='repair_use',
                            quantity=-qty,
                            repair_job=job,
                            note=f"Registered & Issued to Repair Job {job.job_number} (Supplier Udhar: {is_credit})",
                            created_by=request.user if request.user.is_authenticated else None
                        )

                        recalculate_repair_bill(job)
                        snapshot_data = {'part': new_part.name, 'quantity': qty, 'customer_price': str(cust_price), 'supplier': supplier_obj.name if supplier_obj else 'None', 'is_udhar': is_credit}
                        messages.success(request, f"✅ New Part '{new_part.name}' registered from Supplier ({supplier_obj.name if supplier_obj else 'General'}, Udhar: {'Yes' if is_credit else 'No'}) & issued!")

                    # Update status
                    job.status = 'REPAIRING'
                    job.save()

                    # If this was an "Add More Parts" action (not final advance), stay on PARTS_ISSUE
                    if part_action == 'add_part':
                        return redirect('repair_lifecycle_stage', pk=job.id, stage_code='PARTS_ISSUE')

                # 6. QUALITY CHECK STAGE
                elif target_stage == 'QUALITY_CHECK':
                    qc, _ = QualityCheckRecord.objects.get_or_create(repair_job=job)
                    qc.display_ok = request.POST.get('display_ok') in ['true', 'on', '1', True]
                    qc.touch_ok = request.POST.get('touch_ok') in ['true', 'on', '1', True]
                    qc.speaker_mic_ok = request.POST.get('speaker_mic_ok') in ['true', 'on', '1', True]
                    qc.camera_ok = request.POST.get('camera_ok') in ['true', 'on', '1', True]
                    qc.charging_ok = request.POST.get('charging_ok') in ['true', 'on', '1', True]
                    qc.wifi_cellular_ok = request.POST.get('wifi_cellular_ok') in ['true', 'on', '1', True]
                    qc.buttons_ok = request.POST.get('buttons_ok') in ['true', 'on', '1', True]
                    qc.physical_clean_ok = request.POST.get('physical_clean_ok') in ['true', 'on', '1', True]
                    qc.is_passed = request.POST.get('is_passed') in ['true', 'on', '1', True]
                    qc.qc_notes = request.POST.get('qc_notes', '').strip()
                    qc.inspector = request.user if request.user.is_authenticated else None
                    qc.save()

                    if qc.is_passed:
                        job.status = 'QUALITY_CHECK'
                    job.save()

                    snapshot_data = {'is_passed': qc.is_passed, 'notes': qc.qc_notes}
                    messages.success(request, f"Quality check logged: {'PASSED' if qc.is_passed else 'NEEDS RE-WORK'}.")

                # 7. FINAL INVOICE & NOTIFICATION STAGE (COMBINED WITH READY_FOR_DELIVERY)
                elif target_stage in ['FINAL_INVOICE', 'READY_FOR_DELIVERY']:
                    inv = job.invoice
                    disc = Decimal(request.POST.get('discount', '0') or '0')
                    inv.discount = disc
                    recalculate_repair_bill(job)
                    inv.refresh_from_db()
                    
                    job.status = 'READY_FOR_PICKUP'
                    job.save()

                    snapshot_data = {
                        'subtotal': str(inv.subtotal),
                        'discount': str(inv.discount),
                        'total': str(inv.total),
                        'due': str(inv.due_amount),
                        'status': job.status
                    }
                    messages.success(request, "Final invoice saved & job marked READY FOR DELIVERY!")

                # 8. PAYMENT & DELIVERY STAGE
                elif target_stage in ['PAYMENT', 'DELIVERY']:
                    pay_amount = Decimal(request.POST.get('amount', '0') or '0')
                    pay_method = request.POST.get('payment_method', 'cash')
                    pay_notes = request.POST.get('payment_notes', '').strip()

                    inv = job.invoice
                    if pay_amount > 0:
                        Payment.objects.create(
                            invoice=inv,
                            amount=pay_amount,
                            payment_method=pay_method,
                            notes=pay_notes,
                            received_by=request.user if request.user.is_authenticated else None
                        )
                        inv.refresh_from_db()
                        messages.success(request, f"Payment of Rs. {pay_amount:,.2f} recorded.")

                    receiver_name = request.POST.get('receiver_name', '').strip()
                    delivery_note = request.POST.get('delivery_note', '').strip()
                    mark_delivered = request.POST.get('mark_delivered') in ['true', 'on', '1', True] or (inv.due_amount <= 0 and receiver_name)

                    if mark_delivered:
                        job.status = 'DELIVERED'
                        job.save()
                        messages.success(request, f"Job {job.job_number} delivered to customer!")

                    snapshot_data = {
                        'paid_amount': str(pay_amount),
                        'due_amount': str(inv.due_amount),
                        'receiver': receiver_name,
                        'delivery_note': delivery_note,
                        'status': job.status
                    }

                # 9. WARRANTY STAGE
                elif target_stage == 'WARRANTY':
                    warr, _ = WarrantyRecord.objects.get_or_create(repair_job=job)
                    warr.warranty_days = int(request.POST.get('warranty_days', 30) or 30)
                    
                    start_date_raw = request.POST.get('start_date', '').strip()
                    end_date_raw = request.POST.get('end_date', '').strip()
                    
                    if start_date_raw:
                        try:
                            warr.start_date = timezone.datetime.strptime(start_date_raw, '%Y-%m-%d').date()
                        except ValueError:
                            warr.start_date = timezone.now().date()
                    else:
                        warr.start_date = timezone.now().date()
                        
                    if end_date_raw:
                        try:
                            warr.end_date = timezone.datetime.strptime(end_date_raw, '%Y-%m-%d').date()
                        except ValueError:
                            warr.end_date = warr.start_date + timezone.timedelta(days=warr.warranty_days)
                    else:
                        warr.end_date = warr.start_date + timezone.timedelta(days=warr.warranty_days)

                    warr.terms_conditions = request.POST.get('terms_conditions', '').strip()
                    warr.is_active = request.POST.get('is_active', 'true') in ['true', 'on', '1', True]
                    warr.created_by = request.user if request.user.is_authenticated else None
                    warr.save()

                    job.status = 'WARRANTY'
                    job.save()

                    snapshot_data = {
                        'days': warr.warranty_days,
                        'start': str(warr.start_date),
                        'end': str(warr.end_date),
                        'is_active': warr.is_active
                    }
                    messages.success(request, f"Warranty certificate issued ({warr.warranty_days} Days).")

                # 10. COMMISSION CALCULATION STAGE (LAST STEP)
                elif target_stage == 'COMMISSION_CALCULATION':
                    tech_id_raw = request.POST.get('commission_technician_id', '').strip()
                    if tech_id_raw and perm.is_admin:
                        try:
                            t_id = int(tech_id_raw) if tech_id_raw.isdigit() else decode_id(tech_id_raw)
                            selected_tech = Technician.objects.filter(pk=t_id).first()
                            if selected_tech:
                                job.assigned_technician = selected_tech
                                job.save()
                        except Exception:
                            pass

                    if job.assigned_technician:
                        tech_default = getattr(job.assigned_technician, 'default_commission_rate', Decimal('10.00')) or Decimal('10.00')
                        comm = job.commissions.order_by('-created_at').first()
                        if not comm:
                            comm = TechnicianCommissionRecord(
                                repair_job=job,
                                technician=job.assigned_technician,
                                commission_rate=Decimal(str(tech_default))
                            )
                        else:
                            comm.technician = job.assigned_technician

                        is_admin_user = perm.is_admin

                        # Admin can customize type and rate; other users are locked to admin-fixed settings or default 10% of profit
                        if is_admin_user:
                            comm.commission_type = request.POST.get('commission_type', comm.commission_type or 'percentage')
                            comm.commission_rate = Decimal(str(request.POST.get('commission_rate', comm.commission_rate or tech_default) or tech_default))
                        else:
                            comm.commission_rate = Decimal(str(comm.commission_rate or tech_default))
                            if not comm.commission_type:
                                comm.commission_type = 'percentage'

                        inv = getattr(job, 'invoice', None)
                        parts_cost_sum = sum(Decimal(str(p.purchase_cost)) * p.quantity for p in job.parts_used.all()) if job.parts_used.exists() else Decimal('0.00')

                        comm.total_job_revenue = Decimal(str(inv.total if inv else '0.00'))
                        comm.total_parts_cost = Decimal(str(parts_cost_sum))
                        comm.gross_profit = max(Decimal('0.00'), comm.total_job_revenue - comm.total_parts_cost)
                        comm.commission_rate = Decimal(str(comm.commission_rate))

                        if comm.commission_type == 'percentage':
                            comm.commission_amount = (comm.gross_profit * comm.commission_rate) / Decimal('100.00')
                        else:
                            comm.commission_amount = comm.commission_rate

                        if is_admin_user:
                            comm.is_paid = (request.POST.get('is_paid') in ['true', 'on', '1', True])
                        comm.notes = request.POST.get('notes', comm.notes or '').strip()
                        comm.calculated_by = request.user if request.user.is_authenticated else None
                        comm.save()

                        snapshot_data = {
                            'technician': job.assigned_technician.name,
                            'type': comm.commission_type,
                            'rate': str(comm.commission_rate),
                            'gross_profit': str(comm.gross_profit),
                            'commission_amount': str(comm.commission_amount),
                            'is_paid': comm.is_paid
                        }
                        messages.success(request, f"Technician commission saved: Rs. {comm.commission_amount:,.2f} ({comm.commission_rate}% of profit). Full lifecycle completed!")
                    else:
                        messages.warning(request, "No assigned technician found for commission calculation.")

                # Log append-only history record for stage
                stage_info = next((item for item in LIFECYCLE_STAGES_CONFIG if item['code'] == target_stage), None)
                stage_name = stage_info['title'] if stage_info else target_stage

                RepairStageHistory.objects.create(
                    repair_job=job,
                    stage_code=target_stage,
                    stage_name=stage_name,
                    status='COMPLETED',
                    data_snapshot=snapshot_data,
                    note=note or f"Completed {stage_name} stage",
                    created_by=request.user if request.user.is_authenticated else None
                )

                # Also log in RepairStatusHistory
                RepairStatusHistory.objects.create(
                    repair_job=job,
                    old_status=job.status,
                    new_status=job.status,
                    changed_by=request.user if request.user.is_authenticated else None,
                    note=f"Lifecycle Stage [{stage_name}] saved"
                )

                log_audit(request, 'UPDATE', 'RepairJob', job.job_number, details=f"Saved stage {stage_name} (Code: {target_stage})", object_id=job.id)

                # Handle 'advance' step to next screen or finish
                if action == 'advance':
                    if next_stage:
                        job.current_stage = next_stage
                        job.save()
                        messages.info(request, f"Advanced to next stage: {next_stage.replace('_', ' ')}")
                        return redirect('repair_lifecycle_stage', pk=job.id, stage_code=next_stage)
                    else:
                        messages.success(request, f"🎉 Repair Lifecycle fully completed for Job #{job.job_number}!")
                        if hasattr(request.user, 'technician_profile') and request.user.technician_profile and not request.user.is_superuser:
                            return redirect('technician_ess_dashboard')
                        return redirect('repair_detail', pk=job.id)

                return redirect('repair_lifecycle_stage', pk=job.id, stage_code=target_stage)

        except Exception as e:
            messages.error(request, f"Error saving stage {target_stage}: {str(e)}")
            return redirect('repair_lifecycle_stage', pk=job.id, stage_code=target_stage)

    # Context setup for GET rendering
    inspection, _ = InitialInspectionRecord.objects.get_or_create(repair_job=job)
    diagnosis, _ = Diagnosis.objects.get_or_create(repair_job=job)
    estimate = job.estimates.order_by('-updated_at').first()
    if not estimate:
        estimate = RepairEstimate.objects.create(repair_job=job)
    quality_check, _ = QualityCheckRecord.objects.get_or_create(repair_job=job)
    
    is_admin_user = bool(
        request.user.is_superuser or 
        request.user.groups.filter(name__iregex=r'^(admin|administrator|shop\s*manager)$').exists() or
        getattr(request.user, 'role', '').upper() == 'ADMIN'
    )

    suppliers = Supplier.objects.all().order_by('name')
    technicians = Technician.objects.filter(status='active').order_by('name')
    inventory_parts = Part.objects.all().select_related('supplier_fk').order_by('name')
    parts_used = job.parts_used.all().select_related('part', 'part__supplier_fk').order_by('-added_at')
    
    parts_cost_total = sum(Decimal(str(p.purchase_cost)) * p.quantity for p in parts_used) if parts_used.exists() else Decimal('0.00')
    parts_customer_total = sum(Decimal(str(p.customer_price)) * p.quantity for p in parts_used) if parts_used.exists() else Decimal('0.00')
    parts_profit_total = parts_customer_total - parts_cost_total

    inv_total = Decimal(str(job.invoice.total)) if hasattr(job, 'invoice') else Decimal('0.00')
    total_net_profit = max(Decimal('0.00'), inv_total - parts_cost_total)

    commission = job.commissions.order_by('-created_at').first()
    if not commission and job.assigned_technician:
        tech_rate = Decimal(str(getattr(job.assigned_technician, 'default_commission_rate', '10.00') or '10.00'))
        commission = TechnicianCommissionRecord(
            repair_job=job,
            technician=job.assigned_technician,
            commission_type='percentage',
            commission_rate=tech_rate,
            total_job_revenue=inv_total,
            total_parts_cost=parts_cost_total,
            gross_profit=total_net_profit,
            commission_amount=(total_net_profit * tech_rate) / Decimal('100.00')
        )
    elif commission:
        commission.total_job_revenue = inv_total
        commission.total_parts_cost = parts_cost_total
        commission.gross_profit = total_net_profit
        rate = Decimal(str(commission.commission_rate if commission.commission_rate is not None else '10.00'))
        if commission.commission_type == 'percentage':
            commission.commission_amount = (total_net_profit * rate) / Decimal('100.00')
        else:
            commission.commission_amount = rate

    warranty = job.warranties.order_by('-created_at').first()
    if not warranty:
        warranty = WarrantyRecord(repair_job=job, warranty_days=30, start_date=timezone.now().date(), end_date=timezone.now().date() + timezone.timedelta(days=30))

    payments = job.invoice.payments.all().order_by('-created_at') if hasattr(job, 'invoice') else []
    stage_histories = job.stage_histories.all().order_by('-created_at')

    # WhatsApp URLs
    from core.models import ShopSetting
    from core.utils import (
        generate_whatsapp_intake_url,
        generate_whatsapp_final_invoice_url,
        generate_whatsapp_status_url,
        build_whatsapp_chat_url,
        generate_whatsapp_diagnosis_approval_url,
    )
    settings = ShopSetting.get_settings()
    whatsapp_intake_url = generate_whatsapp_intake_url(job, settings)
    whatsapp_final_invoice_url = generate_whatsapp_final_invoice_url(job.invoice, settings, request) if hasattr(job, 'invoice') else ""
    whatsapp_status_url = generate_whatsapp_status_url(job, settings)
    whatsapp_diagnosis_url = generate_whatsapp_diagnosis_approval_url(job, settings, request)
    whatsapp_chat_url = build_whatsapp_chat_url(job.customer.whatsapp or job.customer.phone) if job.customer else ""

    customer_devices = job.customer.devices.all().order_by('-created_at') if job.customer else []

    # 3-Stage Bill / Receipt Viewing Permission Flags:
    # 1. Intake Receipt: CUSTOMER
    # 2. Approval Quotation: CUSTOMER_APPROVAL
    # 3. Final Invoice: FINAL_INVOICE
    show_intake_slip = (stage_code == 'CUSTOMER')
    show_approval_quotation = (stage_code == 'CUSTOMER_APPROVAL')
    show_final_invoice = (stage_code == 'FINAL_INVOICE')

    context = {
        'job': job,
        'customer': job.customer,
        'device': job.device,
        'customer_devices': customer_devices,
        'invoice': getattr(job, 'invoice', None),
        'stages_flow': stages_flow,
        'active_stage_code': stage_code,
        'current_stage_idx': current_stage_idx,
        'prev_stage': prev_stage,
        'next_stage': next_stage,
        'is_stage_locked': is_stage_locked,
        'is_admin_user': is_admin_user,
        'show_intake_slip': show_intake_slip,
        'show_approval_quotation': show_approval_quotation,
        'show_final_invoice': show_final_invoice,
        'inspection': inspection,
        'diagnosis': diagnosis,
        'estimate': estimate,
        'quality_check': quality_check,
        'commission': commission,
        'total_net_profit': total_net_profit,
        'warranty': warranty,
        'technicians': technicians,
        'inventory_parts': inventory_parts,
        'suppliers': suppliers,
        'parts_used': parts_used,
        'parts_cost_total': parts_cost_total,
        'parts_customer_total': parts_customer_total,
        'parts_profit_total': parts_profit_total,
        'payments': payments,
        'stage_histories': stage_histories,
        'payment_methods': Payment.PAYMENT_METHODS,
        'priorities': RepairJob.PRIORITY_CHOICES,
        'whatsapp_intake_url': whatsapp_intake_url,
        'whatsapp_diagnosis_url': whatsapp_diagnosis_url,
        'whatsapp_final_invoice_url': whatsapp_final_invoice_url,
        'whatsapp_status_url': whatsapp_status_url,
        'whatsapp_chat_url': whatsapp_chat_url,
        'is_approval_rejected': is_approval_rejected,
    }

    return render(request, 'repairs/repair_lifecycle.html', context)

@login_required
def diagnosis_thermal_slip(request, pk):
    from core.models import ShopSetting
    job = get_object_or_404(RepairJob.objects.select_related('customer', 'device', 'assigned_technician'), pk=pk)
    diagnosis, _ = Diagnosis.objects.get_or_create(repair_job=job)
    estimate = job.estimates.order_by('-updated_at').first()
    if not estimate:
        estimate = RepairEstimate.objects.create(repair_job=job, estimated_parts_cost=0, estimated_labor_cost=0, total_estimate=0)
    settings = ShopSetting.get_settings()
    today = timezone.localtime(timezone.now()).date()

    return render(request, 'repairs/diagnosis_thermal_slip.html', {
        'job': job,
        'diagnosis': diagnosis,
        'estimate': estimate,
        'settings': settings,
        'today': today,
    })

@login_required
def change_status(request, pk):
    job = get_object_or_404(RepairJob, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        note = request.POST.get('note', '')
        
        if new_status in dict(RepairJob.STATUS_CHOICES):
            # Validation 1: Prevent delivering job with unpaid due amount unless confirmed
            if new_status == 'DELIVERED' and hasattr(job, 'invoice') and job.invoice.due_amount > 0:
                force = request.POST.get('force_delivery') == 'true'
                if not force:
                    messages.error(
                        request,
                        f"⚠️ Cannot mark Job {job.job_number} as DELIVERED because Rs. {job.invoice.due_amount:,.2f} is still unpaid! "
                        f"Please collect payment first."
                    )
                    return redirect('repair_detail', pk=job.id)

            old_status = job.status
            job.status = new_status
            job.save()
            
            # Log in history
            RepairStatusHistory.objects.create(
                repair_job=job,
                old_status=old_status,
                new_status=new_status,
                changed_by=request.user,
                note=note
            )
            
            log_audit(request, 'STATUS_CHANGE', 'RepairJob', job.job_number, details=f"Status changed to {job.get_status_display()} ({note or 'No note'})", object_id=job.id)
            messages.success(request, f"Job {job.job_number} status updated to {job.get_status_display()}.")
            
    return redirect('repair_detail', pk=job.id)

@login_required
def update_diagnosis(request, pk):
    job = get_object_or_404(RepairJob, pk=pk)
    diagnosis = get_object_or_404(Diagnosis, repair_job=job)
    if request.method == 'POST':
        form = DiagnosisForm(request.POST, instance=diagnosis)
        if form.is_valid():
            form.save()
            messages.success(request, "Technician diagnosis logged successfully.")
    return redirect('repair_detail', pk=job.id)

@login_required
def update_estimate(request, pk):
    job = get_object_or_404(RepairJob, pk=pk)
    estimate = job.estimates.order_by('-updated_at').first()
    if request.method == 'POST':
        form = RepairEstimateForm(request.POST, instance=estimate)
        if form.is_valid():
            est = form.save()
            
            # Automatically update the invoice totals
            recalculate_repair_bill(job)
            
            # Update job status if estimate approved
            status_val = form.cleaned_data.get('status')
            if status_val == 'approved' and job.status == 'WAITING_APPROVAL':
                old_st = job.status
                job.status = 'APPROVED'
                job.save()
                RepairStatusHistory.objects.create(
                    repair_job=job,
                    old_status=old_st,
                    new_status='APPROVED',
                    changed_by=request.user,
                    note="Estimate approved by customer"
                )
            
            messages.success(request, f"Repair estimate (Rs. {est.estimated_cost:,.2f}) updated.")
        else:
            err = form.errors.get('estimated_cost', ['Please provide a valid estimated cost.'])[0]
            messages.error(request, str(err))
    return redirect('repair_detail', pk=job.id)

# Technicians CRUD
@login_required
@shop_admin_required
def technician_list(request):
    techs = Technician.objects.all()
    return render(request, 'repairs/technician_list.html', {'technicians': techs})

@login_required
@shop_admin_required
def technician_create(request):
    if request.method == 'POST':
        form = TechnicianForm(request.POST)
        if form.is_valid():
            tech = form.save()
            messages.success(request, f"Technician {tech.name} added successfully.")
            return redirect('technician_list')
    else:
        form = TechnicianForm()
    return render(request, 'repairs/technician_form.html', {'form': form, 'title': 'Add Technician'})

@login_required
@shop_admin_required
def technician_edit(request, pk):
    tech = get_object_or_404(Technician, pk=pk)
    if request.method == 'POST':
        form = TechnicianForm(request.POST, instance=tech)
        if form.is_valid():
            form.save()
            messages.success(request, f"Technician {tech.name} updated.")
            return redirect('technician_list')
    else:
        form = TechnicianForm(instance=tech)
    return render(request, 'repairs/technician_form.html', {'form': form, 'title': 'Edit Technician'})

@login_required
def technician_commissions(request):
    from decimal import Decimal
    from django.db.models import Sum

    if request.method == 'POST' and request.user.is_superuser:
        comm_id = request.POST.get('commission_id')
        if comm_id:
            comm = get_object_or_404(TechnicianCommissionRecord, pk=comm_id)
            comm.is_paid = not comm.is_paid
            comm.save()
            messages.success(request, f"Payout status updated to {'PAID' if comm.is_paid else 'UNPAID'} for {comm.technician.name}.")
            return redirect('technician_commissions')

    if request.user.is_superuser:
        commissions = TechnicianCommissionRecord.objects.select_related('repair_job', 'technician').all().order_by('-created_at')
    elif hasattr(request.user, 'technician_profile') and request.user.technician_profile:
        tech = request.user.technician_profile
        commissions = TechnicianCommissionRecord.objects.select_related('repair_job', 'technician').filter(
            Q(technician=tech) | Q(repair_job__referred_by_technician=tech)
        ).distinct().order_by('-created_at')
    else:
        commissions = TechnicianCommissionRecord.objects.none()

    total_earned = commissions.aggregate(Sum('commission_amount'))['commission_amount__sum'] or Decimal('0.00')
    total_paid = commissions.filter(is_paid=True).aggregate(Sum('commission_amount'))['commission_amount__sum'] or Decimal('0.00')
    total_unpaid = commissions.filter(is_paid=False).aggregate(Sum('commission_amount'))['commission_amount__sum'] or Decimal('0.00')

    return render(request, 'repairs/technician_commissions.html', {
        'commissions': commissions,
        'total_earned': total_earned,
        'total_paid': total_paid,
        'total_unpaid': total_unpaid,
        'is_admin': request.user.is_superuser,
    })

@login_required
@technician_or_admin_required
def technician_ess_dashboard(request):
    from decimal import Decimal
    from django.db.models import Sum, Count

    tech_profile = getattr(request.user, 'technician_profile', None)
    if not tech_profile and request.user.is_superuser:
        tech_profile = Technician.objects.first()

    my_jobs = get_scoped_repair_jobs(request)

    active_jobs_count = my_jobs.filter(~Q(status__in=['DELIVERED', 'CANCELLED', 'RETURNED'])).count()
    completed_jobs_count = my_jobs.filter(status='DELIVERED').count()
    in_repair_count = my_jobs.filter(status='REPAIRING').count()

    if tech_profile:
        my_commissions = TechnicianCommissionRecord.objects.select_related('repair_job', 'technician').filter(
            Q(technician=tech_profile) |
            Q(repair_job__assigned_technician=tech_profile) |
            Q(repair_job__referred_by_technician=tech_profile)
        ).distinct().order_by('-created_at')
    else:
        my_commissions = TechnicianCommissionRecord.objects.none()

    total_earned = my_commissions.aggregate(Sum('commission_amount'))['commission_amount__sum'] or Decimal('0.00')
    pending_payout = my_commissions.filter(is_paid=False).aggregate(Sum('commission_amount'))['commission_amount__sum'] or Decimal('0.00')
    paid_out = my_commissions.filter(is_paid=True).aggregate(Sum('commission_amount'))['commission_amount__sum'] or Decimal('0.00')

    # Supplier Udhar / Credit parts issued in my jobs
    my_job_ids = list(my_jobs.values_list('id', flat=True))
    my_udhar_parts = RepairPart.objects.select_related('part', 'part__supplier_fk', 'repair_job').filter(
        repair_job_id__in=my_job_ids,
        part__is_credit_purchase=True
    ).order_by('-added_at')

    my_supplier_udhar_total = sum(Decimal(str(rp.purchase_cost)) * rp.quantity for rp in my_udhar_parts) if my_udhar_parts.exists() else Decimal('0.00')

    context = {
        'tech_profile': tech_profile,
        'active_jobs_count': active_jobs_count,
        'completed_jobs_count': completed_jobs_count,
        'in_repair_count': in_repair_count,
        'total_earned': total_earned,
        'pending_payout': pending_payout,
        'paid_out': paid_out,
        'recent_jobs': my_jobs[:10],
        'recent_commissions': my_commissions[:10],
        'my_udhar_parts': my_udhar_parts[:10],
        'my_supplier_udhar_total': my_supplier_udhar_total,
    }

    return render(request, 'repairs/technician_ess_dashboard.html', context)

@login_required
def repair_intake_image(request, pk):
    from io import BytesIO
    from django.http import HttpResponse
    from PIL import Image, ImageDraw, ImageFont
    from core.models import ShopSetting

    job = get_object_or_404(RepairJob.objects.select_related('customer', 'device', 'assigned_technician'), pk=pk)
    settings = ShopSetting.get_settings()
    cust = job.customer
    dev = job.device
    estimate = job.estimates.order_by('-updated_at').first()

    def get_font(size, bold=False):
        font_names = ['segoeui.ttf', 'arial.ttf', 'calibri.ttf', 'DejaVuSans.ttf']
        bold_names = ['segoeuib.ttf', 'arialbd.ttf', 'calibrib.ttf', 'DejaVuSans-Bold.ttf']
        target_list = bold_names if bold else font_names
        for name in target_list:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    font_title = get_font(20, bold=True)
    font_badge = get_font(13, bold=True)
    font_bold_14 = get_font(13, bold=True)
    font_bold_12 = get_font(11, bold=True)
    font_regular_12 = get_font(11)
    font_small = get_font(10)

    img_w = 680
    img_h = 620

    img = Image.new('RGB', (img_w, img_h), color='#FFFFFF')
    draw = ImageDraw.Draw(img)

    # Accent top bar
    draw.rectangle([(0, 0), (img_w, 10)], fill='#059669')

    # Header shop info
    draw.text((30, 25), (settings.shop_name or "MOBILE REPAIR SHOP").upper(), fill='#0F172A', font=font_title)
    shop_subtitle = f"Phone: {settings.shop_phone or 'N/A'}"
    if settings.shop_address:
        shop_subtitle += f" | {settings.shop_address}"
    draw.text((30, 54), shop_subtitle[:65], fill='#64748B', font=font_regular_12)

    # Right side badge
    draw.rectangle([(420, 25), (650, 52)], fill='#ECFDF5', outline='#A7F3D0', width=1)
    draw.text((430, 31), f"JOB INTAKE #{job.job_number}", fill='#047857', font=font_badge)

    date_str = job.created_at.strftime('%b %d, %Y, %I:%M %p') if hasattr(job, 'created_at') and job.created_at else 'Today'
    draw.text((430, 58), f"Date: {date_str[:22]}", fill='#64748B', font=font_regular_12)
    draw.text((430, 74), f"Status: {job.get_status_display()}", fill='#059669', font=font_bold_12)

    # Divider
    draw.line([(30, 96), (650, 96)], fill='#E2E8F0', width=2)

    # Customer card
    draw.rectangle([(30, 110), (325, 205)], fill='#F8FAFC', outline='#CBD5E1', width=1)
    draw.text((42, 118), "CUSTOMER DETAILS", fill='#64748B', font=font_small)
    draw.text((42, 134), cust.name[:28], fill='#0F172A', font=font_bold_14)
    draw.text((42, 154), f"Phone: {cust.phone}", fill='#334155', font=font_regular_12)
    if cust.whatsapp:
        draw.text((42, 170), f"WhatsApp: {cust.whatsapp}", fill='#059669', font=font_regular_12)
    draw.text((42, 186), f"City: {cust.address or 'N/A'}"[:28], fill='#64748B', font=font_small)

    # Device card
    draw.rectangle([(345, 110), (650, 205)], fill='#F8FAFC', outline='#CBD5E1', width=1)
    draw.text((357, 118), "DEVICE INFORMATION", fill='#64748B', font=font_small)
    draw.text((357, 134), f"{dev.brand} {dev.model}"[:28], fill='#0F172A', font=font_bold_14)
    draw.text((357, 154), f"IMEI: {dev.imei or 'N/A'}", fill='#334155', font=font_regular_12)
    draw.text((357, 170), f"Color/Storage: {dev.color or '-'}/{dev.storage or '-'}", fill='#64748B', font=font_regular_12)
    draw.text((357, 186), f"Passcode: {dev.device_password or 'None'}", fill='#64748B', font=font_small)

    # Intake details box
    y_box = 220
    draw.rectangle([(30, y_box), (650, y_box + 195)], fill='#F8FAFC', outline='#E2E8F0', width=1)
    draw.text((42, y_box + 12), "CUSTOMER COMPLAINT / PROBLEM", fill='#B91C1C', font=font_bold_12)
    draw.text((42, y_box + 30), job.complaint[:150], fill='#0F172A', font=font_regular_12)

    draw.text((42, y_box + 70), "PHYSICAL CONDITION AT INTAKE", fill='#475569', font=font_bold_12)
    draw.text((42, y_box + 88), (job.physical_condition or dev.physical_condition or "Normal usage marks")[:150], fill='#334155', font=font_regular_12)

    draw.text((42, y_box + 125), "ACCESSORIES RECEIVED", fill='#475569', font=font_bold_12)
    draw.text((42, y_box + 143), (job.accessories or dev.accessories_received or "Device only")[:100], fill='#334155', font=font_regular_12)

    curr = settings.currency or "Rs."
    est_labor = float(estimate.estimated_labor_cost) if estimate and estimate.estimated_labor_cost else 0.00
    est_total = float(estimate.total_estimate) if estimate and estimate.total_estimate else est_labor
    draw.text((42, y_box + 172), f"Initial Quote/Estimate: {curr} {est_total:,.2f}", fill='#059669', font=font_bold_12)

    # Terms & Footer
    y_footer = img_h - 170
    draw.rectangle([(30, y_footer), (650, y_footer + 105)], fill='#FEF2F2', outline='#FECACA', width=1)
    draw.text((42, y_footer + 10), "TERMS & CONDITIONS", fill='#991B1B', font=font_bold_12)
    terms_1 = "1. Please present this slip when collecting your repaired device."
    terms_2 = "2. Shop is not responsible for data loss. Please back up data."
    terms_3 = "3. Devices not claimed within 30 days are subject to disposal policy."
    draw.text((42, y_footer + 30), terms_1, fill='#475569', font=font_regular_12)
    draw.text((42, y_footer + 48), terms_2, fill='#475569', font=font_regular_12)
    draw.text((42, y_footer + 66), terms_3, fill='#475569', font=font_regular_12)

    footer_msg = f"Thank you for choosing {settings.shop_name}! We appreciate your trust."
    draw.text((120, img_h - 35), footer_msg[:75], fill='#64748B', font=font_regular_12)

    buf = BytesIO()
    img.save(buf, format='PNG')
    img_data = buf.getvalue()
    buf.close()

    response = HttpResponse(content_type='image/png')
    response['Content-Disposition'] = f'inline; filename="Intake_Slip_{job.job_number}.png"'
    response.write(img_data)
    return response


@login_required
def diagnosis_image(request, pk):
    """
    Generate crisp, clean PNG image for Diagnosis & Repair Quotation (Approval Slip).
    Sent to customer WhatsApp via pure image copy & paste (No text clutter).
    """
    from io import BytesIO
    from django.http import HttpResponse
    from PIL import Image, ImageDraw, ImageFont
    from core.models import ShopSetting

    job = get_object_or_404(RepairJob.objects.select_related('customer', 'device', 'assigned_technician'), pk=pk)
    diagnosis, _ = Diagnosis.objects.get_or_create(repair_job=job)
    estimate = job.estimates.order_by('-updated_at').first()
    settings = ShopSetting.get_settings()
    cust = job.customer
    dev = job.device

    def get_font(size, bold=False):
        font_names = ['segoeui.ttf', 'arial.ttf', 'calibri.ttf', 'DejaVuSans.ttf']
        bold_names = ['segoeuib.ttf', 'arialbd.ttf', 'calibrib.ttf', 'DejaVuSans-Bold.ttf']
        target_list = bold_names if bold else font_names
        for name in target_list:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    font_title = get_font(20, bold=True)
    font_badge = get_font(13, bold=True)
    font_bold_14 = get_font(13, bold=True)
    font_bold_12 = get_font(11, bold=True)
    font_regular_12 = get_font(11)
    font_small = get_font(10)

    img_w = 680
    img_h = 640

    img = Image.new('RGB', (img_w, img_h), color='#FFFFFF')
    draw = ImageDraw.Draw(img)

    # Accent top bar (Amber/Gold for Diagnosis & Quote)
    draw.rectangle([(0, 0), (img_w, 10)], fill='#D97706')

    # Header shop info
    draw.text((30, 25), (settings.shop_name or "MOBILE REPAIR SHOP").upper(), fill='#0F172A', font=font_title)
    shop_subtitle = f"Phone: {settings.shop_phone or 'N/A'}"
    if settings.shop_address:
        shop_subtitle += f" | {settings.shop_address}"
    draw.text((30, 54), shop_subtitle[:65], fill='#64748B', font=font_regular_12)

    # Right side badge
    draw.rectangle([(400, 25), (650, 52)], fill='#FEF3C7', outline='#FDE68A', width=1)
    draw.text((410, 31), f"DIAGNOSIS & QUOTE #{job.job_number}", fill='#92400E', font=font_badge)

    date_str = job.created_at.strftime('%b %d, %Y') if hasattr(job, 'created_at') and job.created_at else 'Today'
    draw.text((410, 58), f"Date: {date_str[:22]}", fill='#64748B', font=font_regular_12)
    draw.text((410, 74), f"Priority: {job.get_priority_display().upper()}", fill='#D97706', font=font_bold_12)

    # Divider
    draw.line([(30, 96), (650, 96)], fill='#E2E8F0', width=2)

    # Customer card
    draw.rectangle([(30, 110), (325, 205)], fill='#F8FAFC', outline='#CBD5E1', width=1)
    draw.text((42, 118), "CUSTOMER DETAILS", fill='#64748B', font=font_small)
    draw.text((42, 134), cust.name[:28], fill='#0F172A', font=font_bold_14)
    draw.text((42, 154), f"Phone: {cust.phone}", fill='#334155', font=font_regular_12)
    if cust.whatsapp:
        draw.text((42, 170), f"WhatsApp: {cust.whatsapp}", fill='#059669', font=font_regular_12)
    draw.text((42, 186), f"City: {cust.address or 'N/A'}"[:28], fill='#64748B', font=font_small)

    # Device card
    draw.rectangle([(345, 110), (650, 205)], fill='#F8FAFC', outline='#CBD5E1', width=1)
    draw.text((357, 118), "DEVICE INSPECTED", fill='#64748B', font=font_small)
    draw.text((357, 134), f"{dev.brand} {dev.model}"[:28], fill='#0F172A', font=font_bold_14)
    draw.text((357, 154), f"IMEI / SN: {dev.imei or 'N/A'}", fill='#334155', font=font_regular_12)
    draw.text((357, 170), f"Color/Storage: {dev.color or '-'}/{dev.storage or '-'}", fill='#64748B', font=font_regular_12)
    draw.text((357, 186), f"Technician: {job.assigned_technician.name if job.assigned_technician else 'Lab Bench'}"[:28], fill='#64748B', font=font_small)

    # Diagnosis & Recommended Repair box
    y_box = 220
    draw.rectangle([(30, y_box), (650, y_box + 195)], fill='#FFFBEB', outline='#FDE68A', width=1)
    draw.text((42, y_box + 12), "🔍 LAB DIAGNOSIS FINDINGS (Kharabi)", fill='#B45309', font=font_bold_12)
    diag_text = diagnosis.technician_diagnosis if diagnosis and diagnosis.technician_diagnosis else (job.complaint or "Component inspection complete.")
    draw.text((42, y_box + 30), diag_text[:140], fill='#0F172A', font=font_regular_12)

    draw.text((42, y_box + 75), "🛠️ RECOMMENDED REPAIR ACTION (Kaam)", fill='#047857', font=font_bold_12)
    rec_text = diagnosis.recommended_repair if diagnosis and diagnosis.recommended_repair else "Parts replacement and circuit servicing."
    draw.text((42, y_box + 93), rec_text[:140], fill='#0F172A', font=font_regular_12)

    # Quotation Box
    curr = settings.currency or "Rs."
    est_cost = float(estimate.estimated_cost) if estimate and estimate.estimated_cost else 0.00

    draw.line([(42, y_box + 140), (638, y_box + 140)], fill='#FCD34D', width=1)
    draw.text((42, y_box + 155), f"👉 TOTAL ESTIMATED QUOTATION: {curr} {est_cost:,.2f}", fill='#15803D', font=font_bold_14)

    # Terms & Customer Confirmation Prompt
    y_footer = img_h - 190
    draw.rectangle([(30, y_footer), (650, y_footer + 125)], fill='#F8FAFC', outline='#CBD5E1', width=1)
    draw.text((42, y_footer + 10), "CUSTOMER APPROVAL REQUIRED", fill='#0F172A', font=font_bold_12)
    prompt_1 = "• Please review the diagnosis & estimated quotation above."
    prompt_2 = "• Reply with 'YES / APPROVE' on WhatsApp to start repair work."
    prompt_3 = f"• Shop Contact: {settings.shop_phone or 'N/A'}"
    draw.text((42, y_footer + 32), prompt_1, fill='#334155', font=font_regular_12)
    draw.text((42, y_footer + 52), prompt_2, fill='#047857', font=font_bold_12)
    draw.text((42, y_footer + 72), prompt_3, fill='#64748B', font=font_regular_12)

    footer_msg = f"Thank you for choosing {settings.shop_name}! Professional repair services."
    draw.text((120, img_h - 40), footer_msg[:75], fill='#64748B', font=font_regular_12)

    buf = BytesIO()
    img.save(buf, format='PNG')
    img_data = buf.getvalue()
    buf.close()

    response = HttpResponse(content_type='image/png')
    response['Content-Disposition'] = f'inline; filename="Diagnosis_Quote_{job.job_number}.png"'
    response.write(img_data)
    return response
