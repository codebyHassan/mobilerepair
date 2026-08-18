from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.urls import reverse
from django.http import JsonResponse
from decimal import Decimal
from .models import Part, InventoryTransaction, RepairPart, Supplier, SupplierPayment
from .forms import PartForm, InventoryTransactionForm, SupplierForm, SupplierPaymentForm
from core.models import log_audit
from repairs.models import TechnicianCommissionRecord, Technician
from billing.models import Invoice
from repairs.permissions import shop_admin_required

@login_required
@shop_admin_required
def supplier_list(request):
    # Handle technician commission payout toggle directly from the Udhar tabs
    if request.method == 'POST' and request.POST.get('action') == 'toggle_commission':
        comm_id = request.POST.get('commission_id')
        if comm_id:
            comm = get_object_or_404(TechnicianCommissionRecord, pk=comm_id)
            comm.is_paid = not comm.is_paid
            comm.save()
            log_audit(request, 'PAYMENT', 'TechnicianCommission', f"Job #{comm.repair_job.job_number}", details=f"Commission status set to {'PAID' if comm.is_paid else 'UNPAID'} (Rs. {comm.commission_amount:,.2f}) for {comm.technician.name}", object_id=comm.id)
            messages.success(request, f"Payout status updated to {'PAID' if comm.is_paid else 'UNPAID'} for technician {comm.technician.name}.")
            return redirect(f"{reverse('supplier_list')}?tab=technicians")

    query = request.GET.get('q', '')
    active_tab = request.GET.get('tab', 'suppliers')
    
    suppliers_qs = Supplier.objects.all().order_by('-created_at')
    
    if query:
        suppliers_qs = suppliers_qs.filter(
            Q(name__icontains=query) |
            Q(phone__icontains=query) |
            Q(address__icontains=query)
        ).distinct()
        
    total_due_all = sum(float(s.due_balance) for s in suppliers_qs)
    total_paid_all = sum(float(s.total_paid) for s in suppliers_qs)

    # Technician Unpaid Commissions
    unpaid_commissions = TechnicianCommissionRecord.objects.select_related(
        'repair_job', 'technician', 'repair_job__customer', 'repair_job__device'
    ).filter(is_paid=False).order_by('-created_at')

    paid_commissions = TechnicianCommissionRecord.objects.select_related(
        'repair_job', 'technician'
    ).filter(is_paid=True).order_by('-created_at')

    total_tech_unpaid = unpaid_commissions.aggregate(Sum('commission_amount'))['commission_amount__sum'] or Decimal('0.00')
    total_tech_paid = paid_commissions.aggregate(Sum('commission_amount'))['commission_amount__sum'] or Decimal('0.00')

    # Total Overall Liabilities / Payables (Suppliers Udhar + Technician Unpaid Commissions)
    total_overall_payables = float(total_due_all) + float(total_tech_unpaid)

    # Total Customer Receivables
    total_customer_receivables = Invoice.objects.aggregate(Sum('due_amount'))['due_amount__sum'] or Decimal('0.00')
    
    return render(request, 'inventory/supplier_list.html', {
        'suppliers': suppliers_qs,
        'query': query,
        'active_tab': active_tab,
        'total_due_all': total_due_all,
        'total_paid_all': total_paid_all,
        'unpaid_commissions': unpaid_commissions,
        'paid_commissions': paid_commissions,
        'total_tech_unpaid': total_tech_unpaid,
        'total_tech_paid': total_tech_paid,
        'total_overall_payables': total_overall_payables,
        'total_customer_receivables': total_customer_receivables,
    })

@login_required
@shop_admin_required
def supplier_create(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save()
            log_audit(request, 'CREATE', 'Supplier', supplier.name, details=f"Created market supplier {supplier.name} (Phone: {supplier.phone or 'N/A'})", object_id=supplier.id)
            messages.success(request, f"Supplier/Vendor {supplier.name} created successfully.")
            return redirect('supplier_list')
    else:
        form = SupplierForm()
    return render(request, 'inventory/supplier_form.html', {'form': form, 'title': 'Add Market Supplier / Vendor'})

@login_required
@shop_admin_required
def supplier_detail(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    parts_qs = supplier.parts.prefetch_related('repair_uses', 'repair_uses__repair_job').all().order_by('-created_at')
    payments = supplier.payments.all().order_by('-created_at')
    payment_form = SupplierPaymentForm()

    parts_data = []
    for p in parts_qs:
        used_uses = list(p.repair_uses.all())
        qty_used = sum(u.quantity for u in used_uses)
        total_acquired_qty = p.current_stock + qty_used
        if total_acquired_qty == 0:
            total_acquired_qty = 1
        total_cost = float(p.purchase_cost) * total_acquired_qty
        parts_data.append({
            'part': p,
            'current_stock': p.current_stock,
            'qty_used': qty_used,
            'total_acquired_qty': total_acquired_qty,
            'total_cost': total_cost,
            'repair_uses': used_uses,
        })
    
    return render(request, 'inventory/supplier_detail.html', {
        'supplier': supplier,
        'parts': parts_data,
        'payments': payments,
        'payment_form': payment_form,
    })

@login_required
@shop_admin_required
def supplier_payment_create(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        form = SupplierPaymentForm(request.POST)
        if form.is_valid():
            pmt = form.save(commit=False)
            pmt.supplier = supplier
            pmt.paid_by = request.user
            pmt.save()
            log_audit(request, 'PAYMENT', 'SupplierPayment', supplier.name, details=f"Paid vendor Rs. {pmt.amount:,.2f} via {pmt.get_payment_method_display()}", object_id=pmt.id)
            messages.success(request, f"Payment of Rs. {pmt.amount:,.2f} recorded to {supplier.name}.")
            return redirect('supplier_detail', pk=supplier.id)
    return redirect('supplier_detail', pk=supplier.id)

@login_required
def part_list(request):
    query = request.GET.get('q', '')
    category_filter = request.GET.get('category', '')
    
    parts_qs = Part.objects.all().order_by('name')
    
    if category_filter:
        parts_qs = parts_qs.filter(category=category_filter)
        
    if query:
        parts_qs = parts_qs.filter(
            Q(name__icontains=query) |
            Q(sku__icontains=query) |
            Q(compatible_device__icontains=query)
        ).distinct()
        
    # Support JSON response for AJAX dropdown in Repair Details Modal
    if request.GET.get('format') == 'json':
        parts_json = []
        for p in parts_qs.filter(current_stock__gt=0):
            parts_json.append({
                'id': p.id,
                'name': p.name,
                'sku': p.sku,
                'selling_price': float(p.selling_price),
                'current_stock': p.current_stock
            })
        return JsonResponse(parts_json, safe=False)
        
    # Get distinct categories for filters
    categories = Part.objects.values_list('category', flat=True).distinct()
    
    # Calculate statuses and display items
    parts_data = []
    total_value = 0
    low_stock_count = 0
    out_of_stock_count = 0
    
    for p in parts_qs:
        stock_value = p.purchase_cost * p.current_stock
        total_value += stock_value
        
        if p.current_stock == 0:
            status = 'OUT OF STOCK'
            out_of_stock_count += 1
        elif p.current_stock <= p.minimum_stock:
            status = 'LOW STOCK'
            low_stock_count += 1
        else:
            status = 'IN STOCK'
            
        parts_data.append({
            'part': p,
            'status': status,
            'stock_value': stock_value
        })
        
    return render(request, 'inventory/part_list.html', {
        'parts': parts_data,
        'categories': categories,
        'selected_category': category_filter,
        'query': query,
        'total_value': total_value,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'total_products': parts_qs.count()
    })

@login_required
def part_create(request):
    if request.method == 'POST':
        form = PartForm(request.POST)
        if form.is_valid():
            part = form.save()
            
            # Log opening stock transaction if stock > 0
            if part.current_stock > 0:
                InventoryTransaction.objects.create(
                    part=part,
                    transaction_type='purchase',
                    quantity=part.current_stock,
                    note="Initial opening stock setup",
                    created_by=request.user
                )
                
            messages.success(request, f"Spare Part {part.name} added to inventory.")
            return redirect('part_list')
    else:
        form = PartForm()
    return render(request, 'inventory/part_form.html', {'form': form, 'title': 'Add Spare Part'})

@login_required
def part_edit(request, pk):
    part = get_object_or_404(Part, pk=pk)
    if request.method == 'POST':
        form = PartForm(request.POST, instance=part)
        if form.is_valid():
            # Calculate stock adjustment if modified directly
            old_stock = Part.objects.get(pk=pk).current_stock
            part = form.save()
            new_stock = part.current_stock
            
            diff = new_stock - old_stock
            if diff != 0:
                tx_type = 'purchase' if diff > 0 else 'adjustment'
                InventoryTransaction.objects.create(
                    part=part,
                    transaction_type=tx_type,
                    quantity=diff,
                    note="Stock adjustment through direct part profile edit",
                    created_by=request.user
                )
                
            messages.success(request, f"Part {part.name} updated.")
            return redirect('part_list')
    else:
        form = PartForm(instance=part)
    return render(request, 'inventory/part_form.html', {'form': form, 'title': 'Edit Part'})

@login_required
def part_detail(request, pk):
    part = get_object_or_404(Part, pk=pk)
    transactions = part.transactions.all().order_by('-created_at')
    
    status = 'IN STOCK'
    if part.current_stock == 0:
        status = 'OUT OF STOCK'
    elif part.current_stock <= part.minimum_stock:
        status = 'LOW STOCK'
        
    stock_value = part.purchase_cost * part.current_stock
    markup = part.selling_price - part.purchase_cost
    
    return render(request, 'inventory/part_detail.html', {
        'part': part,
        'transactions': transactions,
        'status': status,
        'stock_value': stock_value,
        'markup': markup
    })

@login_required
def transaction_create(request, part_id):
    part = get_object_or_404(Part, pk=part_id)
    if request.method == 'POST':
        form = InventoryTransactionForm(request.POST)
        if form.is_valid():
            tx = form.save(commit=False)
            tx.part = part
            tx.created_by = request.user
            
            # Check quantity validation
            qty = tx.quantity
            if tx.transaction_type in ['repair_use', 'damaged'] and qty > 0:
                qty = -qty  # force subtraction
            
            # Validate stock subtraction
            if part.current_stock + qty < 0:
                messages.error(request, f"Insufficient stock. Cannot adjust by {qty}. Current stock: {part.current_stock}")
                return redirect('part_detail', pk=part.id)
                
            tx.quantity = qty
            tx.save()
            
            # Update part stock
            part.current_stock += qty
            part.save()
            
            messages.success(request, f"Stock transaction recorded successfully. Stock updated to {part.current_stock}.")
            return redirect('part_detail', pk=part.id)
    else:
        form = InventoryTransactionForm()
    return render(request, 'inventory/transaction_form.html', {'form': form, 'part': part})

@login_required
def use_part(request, job_id):
    from repairs.models import RepairJob
    from repairs.views import recalculate_repair_bill
    
    job = get_object_or_404(RepairJob, pk=job_id)
    if job.status in ['DELIVERED', 'CANCELLED', 'RETURNED']:
        messages.error(request, f"Cannot add parts to Job {job.job_number} because it is marked as {job.get_status_display()}.")
        return redirect('repair_detail', pk=job.id)

    if request.method == 'POST':
        part_id = request.POST.get('part_id')
        quantity = int(request.POST.get('quantity', 1))
        from decimal import Decimal
        customer_price = Decimal(request.POST.get('customer_price', '0.00'))
        
        part = get_object_or_404(Part, pk=part_id)
        if part.current_stock < quantity:
            messages.error(request, f"Cannot consume {quantity} of {part.name}. Only {part.current_stock} in stock.")
            return redirect('repair_detail', pk=job.id)
            
        # Subtract stock
        part.current_stock -= quantity
        part.save()
        
        # Log Transaction
        InventoryTransaction.objects.create(
            part=part,
            transaction_type='repair_use',
            quantity=-quantity,
            repair_job=job,
            note=f"Used in Job {job.job_number}",
            created_by=request.user
        )
        
        # Add RepairPart link
        rp, created = RepairPart.objects.get_or_create(
            repair_job=job,
            part=part,
            defaults={
                'quantity': quantity,
                'purchase_cost': part.purchase_cost,
                'customer_price': customer_price
            }
        )
        if not created:
            rp.quantity += quantity
            rp.customer_price = customer_price
            rp.save()
            
        recalculate_repair_bill(job)
        messages.success(request, f"Added part {part.name} x{quantity} to repair.")
        
    return redirect('repair_detail', pk=job.id)

@login_required
def remove_part(request, repair_part_id):
    from repairs.views import recalculate_repair_bill
    
    rp = get_object_or_404(RepairPart, pk=repair_part_id)
    job = rp.repair_job
    if job.status in ['DELIVERED', 'CANCELLED', 'RETURNED']:
        messages.error(request, f"Cannot remove parts from Job {job.job_number} because it is marked as {job.get_status_display()}.")
        return redirect('repair_detail', pk=job.id)
    part = rp.part
    qty = rp.quantity
    
    # Return stock to inventory
    part.current_stock += qty
    part.save()
    
    # Log reverse transaction
    InventoryTransaction.objects.create(
        part=part,
        transaction_type='return',
        quantity=qty,
        repair_job=job,
        note=f"Removed from Job {job.job_number} - Returned stock",
        created_by=request.user
    )
    
    # Remove RepairPart
    rp.delete()
    
    recalculate_repair_bill(job)
    messages.success(request, f"Removed part {part.name} from repair and returned stock to inventory.")
    return redirect('repair_detail', pk=job.id)
