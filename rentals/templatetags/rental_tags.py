from decimal import Decimal, InvalidOperation
from django import template
register = template.Library()

@register.filter
def money(value):
    try:
        amount = Decimal(value)
        return f'{amount:,.0f}' if amount == amount.to_integral_value() else f'{amount:,.2f}'
    except (InvalidOperation, TypeError, ValueError):
        return '0'
