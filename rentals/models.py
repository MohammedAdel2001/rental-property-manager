import builtins
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

POSITIVE = MinValueValidator(Decimal('0.01'))

class Property(models.Model):
    class Kind(models.TextChoices):
        APARTMENT = 'apartment', 'Apartment'
        VILLA = 'villa', 'Villa'
        STUDIO = 'studio', 'Studio'
        OFFICE = 'office', 'Office'

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=80)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.APARTMENT)
    bedrooms = models.PositiveSmallIntegerField(default=1)
    area = models.PositiveIntegerField('Area (m²)', validators=[MinValueValidator(1)], default=80)
    asking_rent = models.DecimalField(max_digits=10, decimal_places=2, validators=[POSITIVE])
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        constraints = [models.CheckConstraint(condition=Q(asking_rent__gt=0), name='positive_asking_rent')]

    def __str__(self):
        return self.name

    @builtins.property
    def current_lease(self):
        today = timezone.localdate()
        return next((lease for lease in self.leases.all() if lease.start_date <= today <= lease.end_date), None)


class Tenant(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @builtins.property
    def initials(self):
        return ''.join(part[0] for part in self.name.split()[:2]).upper()


class Lease(models.Model):
    property = models.ForeignKey(Property, on_delete=models.PROTECT, related_name='leases')
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name='leases')
    start_date = models.DateField()
    end_date = models.DateField()
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2, validators=[POSITIVE])
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date', '-pk']
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gt=models.F('start_date')), name='valid_lease_dates'),
            models.CheckConstraint(condition=Q(monthly_rent__gt=0), name='positive_monthly_rent'),
        ]

    def __str__(self):
        return f'{self.property.name} · {self.tenant.name}'

    @builtins.property
    def status(self):
        today = timezone.localdate()
        return 'Upcoming' if today < self.start_date else 'Expired' if today > self.end_date else 'Active'

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({'end_date': 'End date must be after the start date.'})
        if self.property_id and self.tenant_id and self.property.owner_id != self.tenant.owner_id:
            raise ValidationError('The property and tenant must belong to the same landlord.')
        if self.property_id and self.start_date and self.end_date:
            overlaps = Lease.objects.filter(property_id=self.property_id, start_date__lte=self.end_date, end_date__gte=self.start_date).exclude(pk=self.pk)
            if overlaps.exists():
                raise ValidationError('This property already has a lease during those dates. Choose dates that do not overlap.')
        if self.pk and self.payments.exists():
            original = Lease.objects.get(pk=self.pk)
            if original.property_id != self.property_id or original.tenant_id != self.tenant_id:
                raise ValidationError('A lease with recorded payments cannot be moved to another property or tenant.')
            for payment in self.payments.all():
                if self.start_date and self.end_date and not self.start_date.replace(day=1) <= payment.rent_month <= self.end_date.replace(day=1):
                    raise ValidationError('These dates would exclude an existing payment. Correct the payment first.')
            if self.monthly_rent is not None:
                totals = self.payments.values('rent_month').annotate(total=Sum('amount'))
                if any(row['total'] > self.monthly_rent for row in totals):
                    raise ValidationError('Rent cannot be lower than an amount already collected for a month.')


class Payment(models.Model):
    class Method(models.TextChoices):
        BANK = 'bank', 'Bank transfer'
        CASH = 'cash', 'Cash'
        OTHER = 'other', 'Other'

    lease = models.ForeignKey(Lease, on_delete=models.PROTECT, related_name='payments')
    rent_month = models.DateField(help_text='Choose any date in the month this payment covers.')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[POSITIVE])
    paid_on = models.DateField(default=timezone.localdate)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.BANK)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-paid_on', '-pk']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='positive_payment')]

    def __str__(self):
        return f'{self.lease.property.name} · {self.amount}'

    def clean(self):
        super().clean()
        if self.paid_on and self.paid_on > timezone.localdate():
            raise ValidationError({'paid_on': 'A received payment cannot have a future date.'})
        if self.rent_month:
            self.rent_month = self.rent_month.replace(day=1)
        if self.lease_id and self.rent_month:
            lease = self.lease
            if not lease.start_date.replace(day=1) <= self.rent_month <= lease.end_date.replace(day=1):
                raise ValidationError({'rent_month': 'Choose a month within this lease.'})
            total = Payment.objects.filter(lease_id=self.lease_id, rent_month=self.rent_month).exclude(pk=self.pk).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            if self.amount is not None and total + self.amount > lease.monthly_rent:
                raise ValidationError({'amount': f'This exceeds the remaining rent of {lease.monthly_rent - total:,.2f} for that month.'})
