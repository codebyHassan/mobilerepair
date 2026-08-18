"""
Python 3.14 + Django 4.2 Template Context Copy Patch.
Fixes AttributeError: 'super' object has no attribute 'dicts' when rendering Django Admin templates.
"""
import sys

if sys.version_info >= (3, 14):
    try:
        from django.template.context import BaseContext, Context, RequestContext

        def _patched_context_copy(self):
            duplicate = self.__class__.__new__(self.__class__)
            duplicate.__dict__.update(self.__dict__)
            if hasattr(self, 'dicts'):
                duplicate.dicts = self.dicts[:]
            return duplicate

        BaseContext.__copy__ = _patched_context_copy
        Context.__copy__ = _patched_context_copy
        RequestContext.__copy__ = _patched_context_copy
    except ImportError:
        pass
