from functools import wraps
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404


class RolePermission:
    """
    Role-Based Access Control (RBAC) Property Container for View & Template Logic
    """
    def __init__(self, user):
        self.user = user

    @property
    def is_admin(self):
        if not self.user.is_authenticated:
            return False
        if self.user.is_superuser:
            return True
        if self.user.groups.filter(name__iregex=r'^(admin|administrator|shop\s*manager)$').exists():
            return True
        if getattr(self.user, 'role', '').upper() == 'ADMIN':
            return True
        return False

    @property
    def is_technician(self):
        if not self.user.is_authenticated:
            return False
        if hasattr(self.user, 'technician_profile') and self.user.technician_profile is not None:
            return True
        if self.user.groups.filter(name__iregex=r'^(technician|tech)$').exists():
            return True
        if getattr(self.user, 'role', '').upper() in ['TECHNICIAN', 'TECH']:
            return True
        return False

    @property
    def can_view_all_repairs(self):
        return self.is_admin

    @property
    def can_manage_technicians(self):
        return self.is_admin

    @property
    def can_manage_commissions(self):
        return self.is_admin

    @property
    def can_access_reports(self):
        return self.is_admin

    @property
    def can_view_commissions(self):
        return self.is_admin or self.is_technician

    def can_access_job(self, job):
        if self.is_admin:
            return True
        if self.is_technician and hasattr(self.user, 'technician_profile'):
            tech = self.user.technician_profile
            return (
                job.assigned_technician == tech or
                job.referred_by_technician == tech or
                job.created_by == self.user
            )
        return False


# Dynamically attach RBAC properties to User model
@property
def user_is_technician(self):
    return hasattr(self, 'technician_profile') and self.technician_profile is not None

@property
def user_is_shop_admin(self):
    if not self.is_authenticated:
        return False
    return self.is_superuser or self.groups.filter(name__iregex=r'^(admin|administrator|shop\s*manager)$').exists()

@property
def user_can_view_all_jobs(self):
    return self.user_is_shop_admin

if not hasattr(User, 'is_technician'):
    User.add_to_class('is_technician', user_is_technician)

if not hasattr(User, 'is_shop_admin'):
    User.add_to_class('is_shop_admin', user_is_shop_admin)

if not hasattr(User, 'can_view_all_jobs'):
    User.add_to_class('can_view_all_jobs', user_can_view_all_jobs)


def shop_admin_required(view_func):
    """
    Decorator enforcing Shop Admin privileges on views using property checks
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        perm = RolePermission(request.user)
        if not perm.is_admin:
            messages.error(request, "⛔ Access Restricted: Technician role is restricted from accessing Admin features.")
            if perm.is_technician:
                return redirect('technician_ess_dashboard')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def technician_or_admin_required(view_func):
    """
    Decorator enforcing Technician or Shop Admin permissions on views using property checks
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        perm = RolePermission(request.user)
        if not (perm.is_admin or perm.is_technician):
            messages.error(request, "⛔ Access Restricted: Active Technician or Admin account required.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view
