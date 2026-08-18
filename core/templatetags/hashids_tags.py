from django import template
from core.utils import encode_id, decode_id

register = template.Library()

@register.filter(name='encode_id')
def encode_id_filter(value):
    return encode_id(value)

@register.filter(name='decode_id')
def decode_id_filter(value):
    return decode_id(value)
