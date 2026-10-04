"""Create a fictional portfolio relative to the current month. Safe to run twice."""
import calendar
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from rentals.models import Property, Tenant, Lease, Payment
from rentals.services import shift_month

class Command(BaseCommand):
    help = 'Create the local demo account and fictional sample portfolio (does not overwrite existing data).'

    @transaction.atomic
    def handle(self, *args, **options):
        user, created = get_user_model().objects.get_or_create(username='demo', defaults={'first_name': 'Alex', 'email': 'demo@example.com'})
        if created:
            user.set_password('DemoHome2026!')
            user.save()
        elif Property.objects.filter(owner=user).exists():
            self.stdout.write('Demo portfolio already exists. Nothing was changed.')
            return
        elif not user.check_password('DemoHome2026!'):
            self.stdout.write(self.style.WARNING('An account named demo already exists. No account or data was changed.'))
            return
        today = timezone.localdate()
        month = today.replace(day=1)
        data = [
            ('Garden Apartment', '12 Garden Avenue', 'Maadi', 'apartment', 2, 110, 12000, 'Nour Hassan'),
            ('Maple Residence', '8 Maple Street', 'New Cairo', 'apartment', 3, 165, 18500, 'Omar Khaled'),
            ('Palm Villa', '24 Palm Lane', 'Sheikh Zayed', 'villa', 4, 280, 26000, 'Laila Ahmed'),
            ('River Studio', '6 Riverside Walk', 'Zamalek', 'studio', 0, 55, 9000, 'Youssef Ali'),
            ('Skyline Office', '15 Business Avenue', 'New Cairo', 'office', 0, 95, 15000, 'Sara Mahmoud'),
            ('Willow Apartment', '3 Willow Close', 'Heliopolis', 'apartment', 2, 100, 10500, None),
        ]
        for index, (name, address, city, kind, beds, area, rent, tenant_name) in enumerate(data):
            prop = Property.objects.create(owner=user, name=name, address=address, city=city, kind=kind, bedrooms=beds, area=area, asking_rent=rent, notes='Fictional sample property for the interview demonstration.')
            if tenant_name is None:
                continue
            tenant = Tenant.objects.create(owner=user, name=tenant_name, email=tenant_name.lower().replace(' ', '.') + '@example.com', phone=f'+20 100 000 000{index}', notes='Fictional demo contact.')
            start = shift_month(month, 1 if index == 4 else -5)
            end = shift_month(month, 12 if index == 4 else 6) - timedelta(days=1)
            lease = Lease(property=prop, tenant=tenant, start_date=start, end_date=end, monthly_rent=rent)
            lease.full_clean()
            lease.save()
            if index == 4:
                continue
            for offset in range(-5, 1):
                rent_month = shift_month(month, offset)
                if offset == 0 and index == 2:
                    continue
                amount = Decimal(rent) / 2 if offset == 0 and index == 3 else Decimal(rent)
                received = rent_month.replace(day=min(2 + index, calendar.monthrange(rent_month.year, rent_month.month)[1]))
                if received > today:
                    received = today
                payment = Payment(lease=lease, rent_month=rent_month, amount=amount, paid_on=received, method='cash' if index == 3 else 'bank', reference=f'DEMO-{index + 1}-{rent_month:%Y%m}')
                payment.full_clean()
                payment.save()
        self.stdout.write(self.style.SUCCESS('Demo portfolio created: 6 properties, 5 tenants, 5 leases, 23 payments.'))
        self.stdout.write('Local demo login: demo / DemoHome2026!')
