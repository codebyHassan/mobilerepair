from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.urls import reverse
from .models import Customer, Device
from .forms import CustomerForm, DeviceForm
from billing.models import Invoice
from core.models import log_audit

@login_required
def customer_list(request):
    query = request.GET.get('q', '')
    if query:
        customers_qs = Customer.objects.filter(
            Q(name__icontains=query) | 
            Q(phone__icontains=query) |
            Q(whatsapp__icontains=query)
        ).distinct()
    else:
        customers_qs = Customer.objects.all().order_by('-created_at')

    customers_data = []
    for customer in customers_qs:
        devices_count = customer.devices.count()
        repairs_count = customer.repair_jobs.count()
        
        invoices = Invoice.objects.filter(repair_job__customer=customer)
        total_spent = invoices.aggregate(Sum('total'))['total__sum'] or 0.00
        outstanding = invoices.aggregate(Sum('due_amount'))['due_amount__sum'] or 0.00
        
        last_job = customer.repair_jobs.order_by('-received_date').first()
        last_visit = last_job.received_date if last_job else None
        
        customers_data.append({
            'customer': customer,
            'devices_count': devices_count,
            'repairs_count': repairs_count,
            'total_spent': total_spent,
            'outstanding': outstanding,
            'last_visit': last_visit
        })
        
    return render(request, 'customers/customer_list.html', {
        'customers': customers_data,
        'query': query
    })

@login_required
def customer_create(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            log_audit(request, 'CREATE', 'Customer', customer.name, details=f"Registered customer (Phone: {customer.phone or 'N/A'}, WA: {customer.whatsapp or 'N/A'})", object_id=customer.id)
            messages.success(request, f"Customer {customer.name} created successfully.")
            if 'save_add_device' in request.POST:
                return redirect('device_create', customer_id=customer.id)
            return redirect('customer_detail', pk=customer.id)
    else:
        form = CustomerForm()
    return render(request, 'customers/customer_form.html', {'form': form, 'title': 'Add New Customer'})

@login_required
def customer_edit(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            log_audit(request, 'UPDATE', 'Customer', customer.name, details=f"Updated profile for customer {customer.name}", object_id=customer.id)
            messages.success(request, f"Customer {customer.name} updated successfully.")
            return redirect('customer_detail', pk=customer.id)
    else:
        form = CustomerForm(instance=customer)
    return render(request, 'customers/customer_form.html', {'form': form, 'title': 'Edit Customer'})

@login_required
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    devices = customer.devices.all()
    repairs = customer.repair_jobs.all().order_by('-received_date')
    
    invoices = Invoice.objects.filter(repair_job__customer=customer)
    total_spent = invoices.aggregate(Sum('total'))['total__sum'] or 0.00
    outstanding = invoices.aggregate(Sum('due_amount'))['due_amount__sum'] or 0.00
    
    context = {
        'customer': customer,
        'devices': devices,
        'repairs': repairs,
        'total_spent': total_spent,
        'outstanding': outstanding
    }
    return render(request, 'customers/customer_detail.html', context)

@login_required
def device_create(request, customer_id):
    customer = get_object_or_404(Customer, pk=customer_id)
    if request.method == 'POST':
        form = DeviceForm(request.POST)
        if form.is_valid():
            device = form.save(commit=False)
            device.customer = customer
            device.save()
            log_audit(request, 'CREATE', 'Device', f"{device.brand} {device.model}", details=f"Registered device for {customer.name} (IMEI: {device.imei or 'N/A'})", object_id=device.id)
            messages.success(request, f"Device {device.brand} {device.model} added successfully.")
            if 'save_add_job' in request.POST:
                return redirect(reverse('repair_create') + f"?customer_id={customer.id}&device_id={device.id}")
            return redirect('customer_detail', pk=customer.id)
    else:
        form = DeviceForm()
    return render(request, 'customers/device_form.html', {'form': form, 'customer': customer, 'title': 'Add Device'})

@login_required
def device_edit(request, pk):
    device = get_object_or_404(Device, pk=pk)
    customer = device.customer
    if request.method == 'POST':
        form = DeviceForm(request.POST, instance=device)
        if form.is_valid():
            form.save()
            log_audit(request, 'UPDATE', 'Device', f"{device.brand} {device.model}", details=f"Updated device specs for {customer.name}", object_id=device.id)
            messages.success(request, f"Device {device.brand} {device.model} updated successfully.")
            return redirect('customer_detail', pk=customer.id)
    else:
        form = DeviceForm(instance=device)
    return render(request, 'customers/device_form.html', {'form': form, 'customer': customer, 'title': 'Edit Device'})

@login_required
def customer_devices_api(request, customer_id):
    from django.http import JsonResponse
    customer = get_object_or_404(Customer, pk=customer_id)
    devices = customer.devices.all().order_by('-created_at')
    devices_data = [{
        'id': d.id,
        'brand': d.brand,
        'model': d.model,
        'imei': d.imei or 'N/A',
        'color': d.color or 'N/A',
        'storage': d.storage or 'N/A',
        'physical_condition': d.physical_condition or 'No condition logged'
    } for d in devices]
    return JsonResponse({
        'customer': {'id': customer.id, 'name': customer.name, 'phone': customer.phone or 'N/A'},
        'devices': devices_data
    })

