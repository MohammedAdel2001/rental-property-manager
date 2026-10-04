"""Small reporting functions, kept separate from HTTP views for easy testing."""
import calendar
from datetime import date
from decimal import Decimal
from django.utils import timezone

def shift_month(month, offset):
    index = month.year * 12 + month.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)

def rent_ledger(leases, month, today=None):
    """Full rent per calendar month; first charge is due on the lease start day."""
    today = today or timezone.localdate()
    month = month.replace(day=1)
    end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    rows = []
    for lease in leases:
        if lease.start_date > end or lease.end_date < month:
            continue
        paid = sum((p.amount for p in lease.payments.all() if p.rent_month == month), Decimal('0'))
        balance = max(lease.monthly_rent - paid, Decimal('0'))
        due = max(month, lease.start_date)
        status = 'Paid' if balance == 0 else 'Upcoming' if due > today else 'Partial' if paid else 'Overdue' if due < today else 'Due today'
        rows.append({'lease': lease, 'expected': lease.monthly_rent, 'paid': paid, 'balance': balance, 'due': due, 'status': status})
    return rows
