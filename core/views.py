from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q, F, Sum, Count
from django.utils import timezone
from django.conf import settings
from django.urls import reverse

from .models import ShopSetting, AuditLog, log_audit
from .jwt_auth import generate_user_jwt, decode_user_jwt
from customers.models import Customer, Device
from repairs.models import RepairJob, Technician
from inventory.models import Part
from billing.models import Invoice, Payment
from expenses.models import Expense

class CustomLoginView(LoginView):
    template_name = 'login.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.get_user()
        token = generate_user_jwt(user, session_key=self.request.session.session_key or '')
        self.request.session['jwt_token'] = token
        self.request.session.modified = True
        response.set_cookie(
            'access_token',
            token,
            max_age=getattr(settings, 'JWT_EXPIRY_SECONDS', 1800),
            httponly=True,
            samesite='Lax',
            secure=not settings.DEBUG
        )
        return response

def user_logout(request):
    logout(request)
    if 'jwt_token' in request.session:
        del request.session['jwt_token']
    request.session.flush()

    if request.GET.get('expired'):
        response = redirect(f"{reverse('login')}?expired=1")
        response.delete_cookie('access_token')
        return response

    messages.info(request, "You have been logged out successfully.")
    response = redirect('login')
    response.delete_cookie('access_token')
    return response

@login_required
def session_ping_api(request):
    """
    Heartbeat ping endpoint for active user session refresh with JWT.
    """
    token = generate_user_jwt(request.user, session_key=request.session.session_key or '')
    request.session['jwt_token'] = token
    request.session.modified = True

    response = JsonResponse({
        'status': 'active',
        'user': request.user.username,
        'expires_in_seconds': getattr(settings, 'JWT_EXPIRY_SECONDS', 1800)
    })
    response.set_cookie(
        'access_token',
        token,
        max_age=getattr(settings, 'JWT_EXPIRY_SECONDS', 1800),
        httponly=True,
        samesite='Lax',
        secure=not settings.DEBUG
    )
    return response

@login_required
def dashboard(request):
    from repairs.permissions import RolePermission
    from repairs.models import Technician
    perm = RolePermission(request.user)
    if perm.is_technician and not perm.is_admin:
        if not hasattr(request.user, 'technician_profile') or not request.user.technician_profile:
            Technician.objects.get_or_create(
                user=request.user,
                defaults={'name': request.user.get_full_name() or request.user.username, 'phone': ''}
            )
        return redirect('technician_ess_dashboard')

    settings = ShopSetting.get_settings()
    today = timezone.localtime(timezone.now()).date()
    
    # Repairs metrics combined into a single DB query
    metrics = RepairJob.objects.aggregate(
        total_repairs=Count('id'),
        pending_repairs=Count('id', filter=~Q(status__in=['DELIVERED', 'CANCELLED', 'RETURNED'])),
        repairing=Count('id', filter=Q(status='REPAIRING')),
        ready_for_pickup=Count('id', filter=Q(status='READY_FOR_PICKUP')),
        in_progress_count=Count('id', filter=Q(status__in=['DIAGNOSING', 'WAITING_PARTS', 'REPAIRING'])),
        completed_today=Count('id', filter=Q(status='DELIVERED', updated_at__date=today))
    )
    
    # Financial metrics for today
    today_payments = Payment.objects.filter(created_at__date=today).aggregate(Sum('amount'))['amount__sum'] or 0
    today_expenses = Expense.objects.filter(date=today).aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Outstanding payments (unpaid customer balances only)
    total_outstanding = Invoice.objects.filter(due_amount__gt=0).aggregate(Sum('due_amount'))['due_amount__sum'] or 0
    
    # Low stock items
    low_stock_items = list(Part.objects.filter(current_stock__lte=F('minimum_stock'))[:5])
    low_stock_count = len(low_stock_items)
    
    # Recent repair jobs with select_related to prevent N+1 queries
    recent_jobs = RepairJob.objects.select_related('customer', 'device').order_by('-created_at')[:5]

    # ── SHOP PAYABLES ──────────────────────────────────────────────────────
    # Unpaid technician commissions
    from repairs.models import TechnicianCommissionRecord
    from inventory.models import Supplier

    unpaid_commissions = (
        TechnicianCommissionRecord.objects
        .filter(is_paid=False, commission_amount__gt=0)
        .select_related('technician', 'repair_job', 'repair_job__customer')
        .order_by('-created_at')
    )
    total_unpaid_commission = sum(c.commission_amount for c in unpaid_commissions)

    # Suppliers with Udhar (credit) balance
    suppliers_with_due = [s for s in Supplier.objects.all() if s.due_balance > 0]
    suppliers_with_due.sort(key=lambda s: s.due_balance, reverse=True)
    total_supplier_due = sum(s.due_balance for s in suppliers_with_due)

    context = {
        'settings': settings,
        'total_repairs': metrics['total_repairs'] or 0,
        'pending_repairs': metrics['pending_repairs'] or 0,
        'repairing': metrics['repairing'] or 0,
        'ready_for_pickup': metrics['ready_for_pickup'] or 0,
        'in_progress_count': metrics['in_progress_count'] or 0,
        'completed_today': metrics['completed_today'] or 0,
        'today_payments': today_payments,
        'today_expenses': today_expenses,
        'total_outstanding': total_outstanding,
        'low_stock_count': low_stock_count,
        'low_stock_items': low_stock_items,
        'recent_jobs': recent_jobs,
        # Payables
        'unpaid_commissions': unpaid_commissions,
        'total_unpaid_commission': total_unpaid_commission,
        'suppliers_with_due': suppliers_with_due,
        'total_supplier_due': total_supplier_due,
    }
    return render(request, 'core/dashboard.html', context)

from repairs.permissions import shop_admin_required

@login_required
@shop_admin_required
def settings_view(request):
    settings = ShopSetting.get_settings()
    if request.method == 'POST':
        settings.shop_name = request.POST.get('shop_name', settings.shop_name)
        settings.shop_phone = request.POST.get('shop_phone', settings.shop_phone)
        settings.shop_address = request.POST.get('shop_address', settings.shop_address)
        settings.currency = request.POST.get('currency', settings.currency)
        settings.invoice_prefix = request.POST.get('invoice_prefix', settings.invoice_prefix)
        settings.job_prefix = request.POST.get('job_prefix', settings.job_prefix)
        
        if 'shop_logo' in request.FILES:
            settings.shop_logo = request.FILES['shop_logo']
            
        settings.save()
        messages.success(request, "Settings updated successfully.")
        return redirect('settings_view')
        
    return render(request, 'core/settings.html', {'settings': settings})

@login_required
def global_search_api(request):
    from django.db.models.functions import Coalesce
    from django.db.models import DecimalField, Value
    
    query = request.GET.get('q', '').strip()
    
    if not query:
        customers = Customer.objects.annotate(
            outstanding_due=Coalesce(Sum('repair_jobs__invoice__due_amount'), Value(0, output_field=DecimalField()))
        ).order_by('-created_at')[:10]
    else:
        customers = Customer.objects.filter(
            Q(name__icontains=query) |
            Q(phone__icontains=query) |
            Q(whatsapp__isnull=False, whatsapp__icontains=query)
        ).annotate(
            outstanding_due=Coalesce(Sum('repair_jobs__invoice__due_amount'), Value(0, output_field=DecimalField()))
        ).distinct()[:10]
        
    customers_data = [{
        'id': c.id,
        'name': c.name,
        'phone': c.phone or 'N/A',
        'outstanding': f"{ShopSetting.get_settings().currency} {float(c.outstanding_due or 0):,.2f}"
    } for c in customers]
        
    if not query:
        devices_data, jobs_data, invoices_data = [], [], []
    else:
        devices = Device.objects.select_related('customer').filter(
            Q(brand__icontains=query) | Q(model__icontains=query) | Q(imei__icontains=query)
        )[:5]
        devices_data = [{
            'id': d.id,
            'brand': d.brand,
            'model': d.model,
            'imei': d.imei or 'N/A',
            'customer_name': d.customer.name,
            'customer_id': d.customer.id
        } for d in devices]
        
        jobs = RepairJob.objects.select_related('device').filter(
            Q(job_number__icontains=query) | Q(device__model__icontains=query)
        )[:5]
        jobs_data = [{
            'id': j.id,
            'job_number': j.job_number,
            'device': f"{j.device.brand} {j.device.model}",
            'status': j.get_status_display()
        } for j in jobs]
        
        invoices = Invoice.objects.select_related('repair_job').filter(
            Q(invoice_number__icontains=query) | Q(repair_job__job_number__icontains=query)
        )[:5]
        invoices_data = [{
            'id': inv.id,
            'invoice_number': inv.invoice_number,
            'job_number': inv.repair_job.job_number,
            'due_amount': f"{ShopSetting.get_settings().currency} {inv.due_amount:,.2f}"
        } for inv in invoices]
    
    return JsonResponse({
        'customers': customers_data,
        'devices': devices_data,
        'jobs': jobs_data,
        'invoices': invoices_data
    })

@login_required
@shop_admin_required
def reports_data_api(request):
    from datetime import timedelta
    chart_type = request.GET.get('type', '')
    
    if chart_type == 'trend':
        labels = []
        payments = []
        expenses = []
        
        today = timezone.localtime(timezone.now()).date()
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            labels.append(day.strftime('%a (%b %d)'))
            
            day_payment = Payment.objects.filter(created_at__date=day).aggregate(Sum('amount'))['amount__sum'] or 0.00
            day_expense = Expense.objects.filter(date=day).aggregate(Sum('amount'))['amount__sum'] or 0.00
            
            payments.append(float(day_payment))
            expenses.append(float(day_expense))
            
        return JsonResponse({
            'labels': labels,
            'payments': payments,
            'expenses': expenses
        })
        
    elif chart_type == 'status':
        labels = []
        values = []
        
        for status_val, status_lbl in RepairJob.STATUS_CHOICES:
            count = RepairJob.objects.filter(status=status_val).count()
            if count > 0:
                labels.append(status_lbl)
                values.append(count)
                
        return JsonResponse({
            'labels': labels,
            'values': values
        })
        
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
@shop_admin_required
def reports_home(request):
    today = timezone.localtime(timezone.now()).date()
    month_start = today.replace(day=1)
    
    from inventory.models import Supplier
    from repairs.models import TechnicianCommissionRecord
    
    month_payments = Payment.objects.filter(created_at__date__gte=month_start).aggregate(Sum('amount'))['amount__sum'] or 0.00
    month_expenses = Expense.objects.filter(date__gte=month_start).aggregate(Sum('amount'))['amount__sum'] or 0.00
    
    total_customer_due = Invoice.objects.aggregate(Sum('due_amount'))['due_amount__sum'] or 0.00
    suppliers = Supplier.objects.all()
    total_vendor_due = sum(s.due_balance for s in suppliers)
    
    total_tech_unpaid_commissions = TechnicianCommissionRecord.objects.filter(is_paid=False).aggregate(Sum('commission_amount'))['commission_amount__sum'] or 0.00
    total_shop_payables = float(total_vendor_due) + float(total_tech_unpaid_commissions)
    
    recent_payments = Payment.objects.select_related('invoice', 'invoice__repair_job', 'invoice__repair_job__customer').order_by('-created_at')[:6]
    
    context = {
        'today': today,
        'month_payments': month_payments,
        'month_expenses': month_expenses,
        'month_net': float(month_payments) - float(month_expenses),
        'total_customer_due': total_customer_due,
        'total_vendor_due': total_vendor_due,
        'total_tech_unpaid_commissions': total_tech_unpaid_commissions,
        'total_shop_payables': total_shop_payables,
        'recent_payments': recent_payments,
    }
    return render(request, 'core/reports_home.html', context)

@login_required
@shop_admin_required
def daily_report(request):
    today = timezone.localtime(timezone.now()).date()
    
    jobs_received = RepairJob.objects.filter(received_date__date=today)
    jobs_delivered = RepairJob.objects.filter(status_history__new_status='DELIVERED', status_history__timestamp__date=today).distinct()
    
    payments = Payment.objects.filter(created_at__date=today)
    total_payments = payments.aggregate(Sum('amount'))['amount__sum'] or 0.00
    
    from inventory.models import RepairPart
    from repairs.models import TechnicianCommissionRecord
    parts_today = RepairPart.objects.filter(added_at__date=today)
    parts_cost = parts_today.aggregate(Sum('purchase_cost'))['purchase_cost__sum'] or 0.00
    
    commissions_today = TechnicianCommissionRecord.objects.filter(created_at__date=today).aggregate(Sum('commission_amount'))['commission_amount__sum'] or 0.00
    
    expenses = Expense.objects.filter(date=today)
    total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or 0.00
    
    context = {
        'today': today,
        'jobs_received': jobs_received,
        'jobs_delivered': jobs_delivered,
        'total_payments': total_payments,
        'parts_cost': parts_cost,
        'commissions_today': commissions_today,
        'total_expenses': total_expenses,
    }
    return render(request, 'core/daily_report.html', context)

@login_required
@shop_admin_required
def monthly_profit_loss(request):
    today = timezone.localtime(timezone.now()).date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
    from repairs.models import TechnicianCommissionRecord
    
    jobs = RepairJob.objects.filter(
        created_at__year=year, 
        created_at__month=month,
        status__in=['DELIVERED', 'READY_FOR_PICKUP']
    )
    
    total_revenue = 0.00
    total_parts_cost = 0.00
    total_labor_cost = 0.00
    
    for job in jobs:
        if hasattr(job, 'invoice'):
            total_revenue += float(job.invoice.total)
            
        job_parts_cost = job.parts_used.aggregate(
            cost=Sum(F('purchase_cost') * F('quantity'))
        )['cost'] or 0.00
        total_parts_cost += float(job_parts_cost)
        
        est = job.estimates.order_by('-updated_at').first()
        if est:
            total_labor_cost += float(est.estimated_labor_cost)
            
    gross_profit = total_revenue - total_parts_cost
    
    commissions_month = TechnicianCommissionRecord.objects.filter(
        created_at__year=year, created_at__month=month
    ).aggregate(Sum('commission_amount'))['commission_amount__sum'] or 0.00
    commissions_month = float(commissions_month)
    
    expenses_sum = Expense.objects.filter(date__year=year, date__month=month).aggregate(Sum('amount'))['amount__sum'] or 0.00
    expenses_sum = float(expenses_sum)
    net_profit = gross_profit - expenses_sum - commissions_month
    
    months = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
    ]
    
    context = {
        'year': year,
        'month': month,
        'month_name': dict(months).get(month),
        'total_revenue': total_revenue,
        'total_parts_cost': total_parts_cost,
        'total_labor_cost': total_labor_cost,
        'commissions_month': commissions_month,
        'gross_profit': gross_profit,
        'expenses_sum': expenses_sum,
        'net_profit': net_profit,
        'months': months,
        'years': range(today.year - 2, today.year + 2),
    }
    return render(request, 'core/profit_loss_report.html', context)

@login_required
@shop_admin_required
def audit_log_list(request):
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "Access restricted. Superadmin privileges required.")
        return redirect('dashboard')
        
    from core.models import AuditLog
    query = request.GET.get('q', '')
    user_filter = request.GET.get('user', '')
    action_filter = request.GET.get('action', '')
    model_filter = request.GET.get('model', '')
    
    logs_qs = AuditLog.objects.select_related('user').all().order_by('-timestamp')
    
    if query:
        logs_qs = logs_qs.filter(
            Q(object_repr__icontains=query) |
            Q(details__icontains=query) |
            Q(user__username__icontains=query)
        ).distinct()
        
    if user_filter:
        logs_qs = logs_qs.filter(user_id=user_filter)
        
    if action_filter:
        logs_qs = logs_qs.filter(action=action_filter)
        
    if model_filter:
        logs_qs = logs_qs.filter(model_name=model_filter)
        
    from django.contrib.auth.models import User
    users = User.objects.all().order_by('username')
    action_choices = AuditLog.ACTION_CHOICES
    
    from django.core.paginator import Paginator
    paginator = Paginator(logs_qs, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'core/audit_log_list.html', {
        'page_obj': page_obj,
        'query': query,
        'users': users,
        'selected_user': user_filter,
        'selected_action': action_filter,
        'selected_model': model_filter,
        'action_choices': action_choices,
        'total_logs': logs_qs.count(),
    })

def custom_404_view(request, exception=None):
    return render(request, '404.html', status=404)

@login_required
def user_profile(request):
    user = request.user
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'profile_info':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()

            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.save()

            log_audit(request, 'UPDATE', 'User', user.username, details=f"Updated profile details for {user.username}", object_id=user.id)
            messages.success(request, "Your profile details have been successfully updated!")
            return redirect('user_profile')

    return render(request, 'core/user_profile.html', {
        'profile_user': user,
    })

@login_required
def change_password(request):
    from django.contrib.auth import update_session_auth_hash

    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password1 = request.POST.get('new_password1', '')
        new_password2 = request.POST.get('new_password2', '')

        user = request.user

        if not user.check_password(old_password):
            messages.error(request, "Incorrect current password. Please try again.")
            return redirect('user_profile')

        if new_password1 != new_password2:
            messages.error(request, "New passwords do not match. Please re-enter.")
            return redirect('user_profile')

        if len(new_password1) < 6:
            messages.error(request, "Password must be at least 6 characters long.")
            return redirect('user_profile')

        user.set_password(new_password1)
        user.save()
        update_session_auth_hash(request, user)

        log_audit(request, 'UPDATE', 'User', user.username, details=f"Changed password for {user.username}", object_id=user.id)
        messages.success(request, "🔒 Password updated successfully! Your account is now secured with the new password.")
        return redirect('user_profile')

    return redirect('user_profile')


