from django.db import models
from django.contrib.auth.models import User

class ShopSetting(models.Model):
    shop_name = models.CharField(max_length=255, default='MobileFix Pro')
    shop_phone = models.CharField(max_length=50, blank=True)
    shop_address = models.TextField(blank=True)
    shop_logo = models.ImageField(upload_to='shop_logo/', blank=True, null=True)
    currency = models.CharField(max_length=10, default='Rs.')
    invoice_prefix = models.CharField(max_length=10, default='INV')
    job_prefix = models.CharField(max_length=10, default='JOB')

    @classmethod
    def get_settings(cls):
        obj, created = cls.objects.get_or_create(id=1)
        return obj

    def __str__(self):
        return self.shop_name

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Created Record'),
        ('UPDATE', 'Updated Record'),
        ('DELETE', 'Deleted Record'),
        ('STATUS_CHANGE', 'Status Changed'),
        ('PAYMENT', 'Payment Logged'),
        ('WHATSAPP', 'WhatsApp Sent'),
        ('LOGIN', 'User Login'),
        ('OTHER', 'Other Action'),
    ]
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, db_index=True)
    model_name = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=100, blank=True, null=True)
    object_repr = models.CharField(max_length=255, blank=True, null=True)
    details = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        user_str = self.user.username if self.user else "System"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {user_str} - {self.action} {self.model_name}: {self.object_repr}"

def log_audit(request_or_user, action, model_name, object_repr, details="", object_id="", ip=None):
    user = None
    ip_addr = ip

    if hasattr(request_or_user, 'user'):
        request = request_or_user
        if request.user and request.user.is_authenticated:
            user = request.user
        if not ip_addr:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_addr = x_forwarded_for.split(',')[0].strip()
            else:
                ip_addr = request.META.get('REMOTE_ADDR')
    elif isinstance(request_or_user, User):
        user = request_or_user

    try:
        return AuditLog.objects.create(
            user=user,
            action=action,
            model_name=model_name,
            object_id=str(object_id) if object_id else "",
            object_repr=str(object_repr)[:250] if object_repr else "",
            details=details,
            ip_address=ip_addr
        )
    except Exception as e:
        print("Audit logging error:", e)
        return None
