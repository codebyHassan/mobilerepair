from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from .models import Expense, ExpenseCategory
from .forms import ExpenseForm, ExpenseCategoryForm
from repairs.permissions import shop_admin_required

@login_required
@shop_admin_required
def expense_list(request):
    expenses_qs = Expense.objects.all().order_by('-date', '-created_at')
    
    # Date filters
    filter_type = request.GET.get('date_filter', 'all')
    today = timezone.localtime(timezone.now()).date()
    start_date_val = None
    end_date_val = None
    
    if filter_type == 'today':
        expenses_qs = expenses_qs.filter(date=today)
    elif filter_type == 'week':
        start_date = today - timedelta(days=today.weekday())
        expenses_qs = expenses_qs.filter(date__gte=start_date)
    elif filter_type == 'month':
        expenses_qs = expenses_qs.filter(date__year=today.year, date__month=today.month)
    elif filter_type == 'custom':
        start_date_val = request.GET.get('start_date')
        end_date_val = request.GET.get('end_date')
        if start_date_val and end_date_val:
            expenses_qs = expenses_qs.filter(date__range=[start_date_val, end_date_val])
            
    # Calculate stats
    today_expenses = Expense.objects.filter(date=today).aggregate(Sum('amount'))['amount__sum'] or 0.00
    month_expenses = Expense.objects.filter(date__year=today.year, date__month=today.month).aggregate(Sum('amount'))['amount__sum'] or 0.00
    total_filtered = expenses_qs.aggregate(Sum('amount'))['amount__sum'] or 0.00
    
    # Group by category for the filtered list
    category_summary = expenses_qs.values('category__name').annotate(cat_total=Sum('amount')).order_by('-cat_total')
    
    return render(request, 'expenses/expense_list.html', {
        'expenses': expenses_qs,
        'today_expenses': today_expenses,
        'month_expenses': month_expenses,
        'total_filtered': total_filtered,
        'category_summary': category_summary,
        'filter_type': filter_type,
        'start_date': start_date_val,
        'end_date': end_date_val,
    })

@login_required
@shop_admin_required
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save()
            messages.success(request, f"Expense of Rs. {expense.amount} under '{expense.category.name}' logged successfully.")
            return redirect('expense_list')
    else:
        form = ExpenseForm(initial={'date': timezone.localtime(timezone.now()).date()})
    return render(request, 'expenses/expense_form.html', {'form': form, 'title': 'Log Shop Expense'})

@login_required
@shop_admin_required
def category_list(request):
    categories = ExpenseCategory.objects.all().order_by('name')
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f"Expense category '{cat.name}' created.")
            return redirect('expense_category_list')
    else:
        form = ExpenseCategoryForm()
        
    return render(request, 'expenses/category_list.html', {
        'categories': categories,
        'form': form
    })
