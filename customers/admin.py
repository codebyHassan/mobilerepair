from django.contrib import admin
from .models import Customer, Device

class DeviceInline(admin.TabularInline):
    model = Device
    extra = 1
    fields = ('brand', 'model', 'imei', 'color', 'storage')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'whatsapp', 'email', 'get_devices_count', 'get_jobs_count', 'created_at')
    search_fields = ('name', 'phone', 'whatsapp', 'email')
    list_filter = ('created_at',)
    inlines = [DeviceInline]
    ordering = ('-created_at',)

    @admin.display(description='Devices Registered')
    def get_devices_count(self, obj):
        return obj.devices.count()

    @admin.display(description='Repair Jobs')
    def get_jobs_count(self, obj):
        return obj.repair_jobs.count()

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('brand', 'model', 'customer', 'imei', 'color', 'storage', 'created_at')
    search_fields = ('brand', 'model', 'imei', 'customer__name', 'customer__phone')
    list_filter = ('brand', 'created_at')
    autocomplete_fields = ['customer']
    ordering = ('-created_at',)
