from django.contrib import admin
from .models import ExpenseCategory, Expense

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('category', 'amount', 'payment_method', 'date', 'description')
    list_filter = ('category', 'payment_method', 'date')
    search_fields = ('category__name', 'description', 'payment_method')
    list_editable = ('amount', 'payment_method', 'date')
