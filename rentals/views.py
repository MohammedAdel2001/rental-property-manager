import csv
from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.deletion import ProtectedError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .forms import PropertyForm, TenantForm, LeaseForm, PaymentForm
from .models import Property, Tenant, Lease, Payment
from .services import rent_ledger, shift_month

ENTITIES = {
    'properties': (Property, PropertyForm, 'Property', 'Properties', 'Spaces with potential. Everything you manage, in one place.'),
    'tenants': (Tenant, TenantForm, 'Tenant', 'Tenants', 'Good relationships start with keeping the details together.'),
    'leases': (Lease, LeaseForm, 'Lease', 'Leases', 'Clear agreements. Confident property management.'),
    'payments': (Payment, PaymentForm, 'Payment', 'Payments', 'Every payment recorded. Every month accounted for.'),
}

def config(entity):
    if entity not in ENTITIES:
        raise Http404
    return ENTITIES[entity]

def owned(entity, user):
    model = config(entity)[0]
    if entity == 'properties':
        return model.objects.filter(owner=user).prefetch_related('leases__tenant')
    if entity == 'tenants':
        return model.objects.filter(owner=user).prefetch_related('leases__property')
    if entity == 'leases':
        return model.objects.filter(property__owner=user).select_related('property', 'tenant').prefetch_related('payments')
    return model.objects.filter(lease__property__owner=user).select_related('lease__property', 'lease__tenant')

def month_from_request(request):
    try:
        return date.fromisoformat(request.GET.get('month', '') + '-01')
    except ValueError:
        return timezone.localdate().replace(day=1)

@login_required
def dashboard(request):
    today = timezone.localdate()
    month = today.replace(day=1)
    properties = list(owned('properties', request.user))
    leases = list(owned('leases', request.user))
    payments = owned('payments', request.user)
    ledger = rent_ledger(leases, month)
    expected = sum((r['expected'] for r in ledger), Decimal('0'))
    collected = sum((r['paid'] for r in ledger), Decimal('0'))
    outstanding = sum((r['balance'] for r in ledger), Decimal('0'))
    occupied = sum(1 for p in properties if p.current_lease)
    cash_received = payments.filter(paid_on__year=month.year, paid_on__month=month.month).aggregate(total=Sum('amount'))['total'] or 0
    chart = []
    for offset in range(-5, 1):
        chart_month = shift_month(month, offset)
        total = payments.filter(paid_on__gte=chart_month, paid_on__lt=shift_month(chart_month, 1)).aggregate(total=Sum('amount'))['total'] or 0
        chart.append({'month': chart_month, 'total': total})
    maximum = max((row['total'] for row in chart), default=0) or 1
    for row in chart:
        row['height'] = max(2, round(row['total'] / maximum * 100))
    attention = sorted((r for r in ledger if r['balance'] > 0), key=lambda r: r['due'])
    return render(request, 'rentals/dashboard.html', {
        'section': 'dashboard', 'properties': properties[:3], 'property_count': len(properties),
        'occupied': occupied, 'vacant': len(properties) - occupied,
        'occupancy': round(occupied / len(properties) * 100) if properties else 0,
        'tenant_count': Tenant.objects.filter(owner=request.user).count(),
        'active_count': sum(1 for l in leases if l.status == 'Active'),
        'expected': expected, 'collected': collected, 'outstanding': outstanding,
        'collection_rate': round(collected / expected * 100) if expected else 0,
        'cash_received': cash_received, 'chart': chart,
        'attention': attention[:4], 'attention_count': len(attention),
        'recent_payments': payments[:5],
    })

@login_required
def record_list(request, entity):
    model, form, singular, plural, subtitle = config(entity)
    queryset = owned(entity, request.user)
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    if query:
        if entity == 'properties':
            queryset = queryset.filter(Q(name__icontains=query) | Q(address__icontains=query) | Q(city__icontains=query))
        elif entity == 'tenants':
            queryset = queryset.filter(Q(name__icontains=query) | Q(email__icontains=query) | Q(phone__icontains=query))
        elif entity == 'leases':
            queryset = queryset.filter(Q(property__name__icontains=query) | Q(tenant__name__icontains=query))
        else:
            queryset = queryset.filter(Q(lease__property__name__icontains=query) | Q(lease__tenant__name__icontains=query) | Q(reference__icontains=query))
    today = timezone.localdate()
    if entity == 'properties' and status in ('occupied', 'vacant'):
        active = Lease.objects.filter(start_date__lte=today, end_date__gte=today).values('property_id')
        queryset = queryset.filter(pk__in=active) if status == 'occupied' else queryset.exclude(pk__in=active)
    elif entity == 'leases':
        if status == 'active':
            queryset = queryset.filter(start_date__lte=today, end_date__gte=today)
        elif status == 'upcoming':
            queryset = queryset.filter(start_date__gt=today)
        elif status == 'expired':
            queryset = queryset.filter(end_date__lt=today)
    elif entity == 'payments' and request.GET.get('month'):
        month = month_from_request(request)
        queryset = queryset.filter(rent_month=month)
    page = Paginator(queryset, 9 if entity == 'properties' else 12).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'rentals/list.html', {
        'section': entity, 'entity': entity, 'singular': singular, 'title': plural,
        'subtitle': subtitle, 'page_obj': page, 'q': query, 'status': status,
        'query_params': params.urlencode(), 'selected_month': request.GET.get('month', ''),
    })

@login_required
def record_detail(request, entity, pk):
    config(entity)
    obj = get_object_or_404(owned(entity, request.user), pk=pk)
    context = {'section': entity, 'entity': entity, 'obj': obj, 'singular': config(entity)[2]}
    if entity in ('properties', 'tenants'):
        context['leases'] = obj.leases.select_related('property', 'tenant')
    elif entity == 'leases':
        context['payments'] = obj.payments.all()
        context['ledger'] = rent_ledger([obj], timezone.localdate().replace(day=1))
    return render(request, 'rentals/detail.html', context)

@login_required
def record_form(request, entity, pk=None):
    model, form_class, singular, plural, subtitle = config(entity)
    obj = get_object_or_404(owned(entity, request.user), pk=pk) if pk else None
    initial = {}
    if not pk and entity == 'payments':
        initial['rent_month'] = timezone.localdate().replace(day=1)
        if request.GET.get('lease', '').isdigit():
            lease = get_object_or_404(owned('leases', request.user), pk=request.GET['lease'])
            initial['lease'] = lease
    if not pk and entity == 'leases' and request.GET.get('property', '').isdigit():
        property_obj = get_object_or_404(owned('properties', request.user), pk=request.GET['property'])
        initial.update(property=property_obj, monthly_rent=property_obj.asking_rent)
    # Validation and write share a transaction. This is a small, local SQLite application.
    with transaction.atomic():
        form = form_class(request.POST if request.method == 'POST' else None, instance=obj, user=request.user, initial=initial)
        if request.method == 'POST' and form.is_valid():
            record = form.save(commit=False)
            if entity in ('properties', 'tenants'):
                record.owner = request.user
            record.save()
            messages.success(request, f'{singular} {"updated" if pk else "added"} successfully.')
            return redirect('record_detail', entity=entity, pk=record.pk)
    return render(request, 'rentals/form.html', {
        'section': entity, 'entity': entity, 'form': form, 'obj': obj,
        'singular': singular, 'title': f'{"Edit" if pk else "Add"} {singular.lower()}',
    })

@login_required
def record_delete(request, entity, pk):
    obj = get_object_or_404(owned(entity, request.user), pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, f'{config(entity)[2]} deleted.')
            return redirect('record_list', entity=entity)
        except ProtectedError:
            messages.error(request, 'This record has linked leases or payments. Remove those records first if you really intend to delete its history.')
            return redirect('record_detail', entity=entity, pk=pk)
    return render(request, 'rentals/delete.html', {'section': entity, 'entity': entity, 'obj': obj, 'singular': config(entity)[2]})

@login_required
def rent_roll(request):
    month = month_from_request(request)
    rows = rent_ledger(owned('leases', request.user), month)
    return render(request, 'rentals/rent_roll.html', {
        'section': 'rent_roll', 'rows': rows, 'month': month,
        'expected': sum((r['expected'] for r in rows), Decimal('0')),
        'paid': sum((r['paid'] for r in rows), Decimal('0')),
        'balance': sum((r['balance'] for r in rows), Decimal('0')),
    })

def csv_safe(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text

@login_required
def export_payments(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="rental-payments.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Property', 'Tenant', 'Rent month', 'Amount', 'Paid on', 'Method', 'Reference'])
    for p in owned('payments', request.user):
        writer.writerow([csv_safe(p.lease.property.name), csv_safe(p.lease.tenant.name), p.rent_month, p.amount, p.paid_on, p.get_method_display(), csv_safe(p.reference)])
    return response
