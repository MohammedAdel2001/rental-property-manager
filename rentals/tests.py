from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from io import StringIO
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db.models.deletion import ProtectedError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Property, Tenant, Lease, Payment
from .forms import PaymentForm, LeaseForm
from .services import rent_ledger, shift_month

class RentalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user('landlord', password='Test-password-2026')
        cls.other = get_user_model().objects.create_user('other', password='Test-password-2026')
        cls.month = timezone.localdate().replace(day=1)
        cls.prop = Property.objects.create(owner=cls.owner, name='Garden House', address='1 Garden Street', city='Cairo', asking_rent=1000)
        cls.tenant = Tenant.objects.create(owner=cls.owner, name='Test Tenant', email='tenant@example.com', phone='01000000000')
        cls.lease = Lease.objects.create(property=cls.prop, tenant=cls.tenant, start_date=shift_month(cls.month, -2), end_date=shift_month(cls.month, 3), monthly_rent=1000)
        cls.foreign_prop = Property.objects.create(owner=cls.other, name='Private Property', address='2 Other Street', city='Cairo', asking_rent=1000)
        cls.foreign_tenant = Tenant.objects.create(owner=cls.other, name='Private Tenant', email='private@example.com', phone='01000000001')
        cls.foreign_lease = Lease.objects.create(property=cls.foreign_prop, tenant=cls.foreign_tenant, start_date=cls.month, end_date=shift_month(cls.month, 2), monthly_rent=1000)
        cls.foreign_payment = Payment.objects.create(lease=cls.foreign_lease, rent_month=cls.month, amount=100, paid_on=timezone.localdate())

    def setUp(self):
        self.client.force_login(self.owner)

    def payment(self, amount=300, **kwargs):
        values = dict(lease=self.lease, rent_month=self.month, amount=Decimal(amount), paid_on=timezone.localdate())
        values.update(kwargs)
        payment = Payment(**values)
        payment.full_clean()
        payment.save()
        return payment

    def test_all_pages_render(self):
        payment = self.payment()
        records = {'properties': self.prop, 'tenants': self.tenant, 'leases': self.lease, 'payments': payment}
        for entity, obj in records.items():
            for url in (f'/{entity}/', f'/{entity}/add/', f'/{entity}/{obj.pk}/', f'/{entity}/{obj.pk}/edit/', f'/{entity}/{obj.pk}/delete/'):
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
        for url in ('/', '/rent-roll/', '/payments/export/'):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_login_required(self):
        self.client.logout()
        for url in ('/', '/properties/', '/tenants/', '/leases/', '/payments/', '/rent-roll/', '/payments/export/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_login_and_logout(self):
        self.client.logout()
        self.assertEqual(self.client.get('/login/').status_code, 200)
        self.assertEqual(self.client.post('/login/', {'username': 'landlord', 'password': 'Test-password-2026'}).status_code, 302)
        self.assertEqual(self.client.get('/logout/').status_code, 405)
        self.assertEqual(self.client.post('/logout/').status_code, 302)

    def test_other_owner_records_are_hidden(self):
        records = {'properties': self.foreign_prop, 'tenants': self.foreign_tenant, 'leases': self.foreign_lease, 'payments': self.foreign_payment}
        for entity, obj in records.items():
            self.assertNotContains(self.client.get(f'/{entity}/'), 'Private')
            for suffix in ('', 'edit/', 'delete/'):
                self.assertEqual(self.client.get(f'/{entity}/{obj.pk}/{suffix}').status_code, 404)
                self.assertEqual(self.client.post(f'/{entity}/{obj.pk}/{suffix}', {}).status_code, 404)
        self.assertNotContains(self.client.get('/'), 'Private')
        self.assertNotContains(self.client.get('/rent-roll/'), 'Private')
        self.assertNotContains(self.client.get('/payments/export/'), 'Private')

    def test_property_create_ignores_forged_owner(self):
        response = self.client.post('/properties/add/', {'owner': self.other.pk, 'name': 'New House', 'address': '3 Main Road', 'city': 'Cairo', 'kind': 'villa', 'bedrooms': 3, 'area': 120, 'asking_rent': '1500', 'notes': ''})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Property.objects.get(name='New House').owner, self.owner)

    def test_property_update_and_delete_workflow(self):
        prop = Property.objects.create(owner=self.owner, name='Disposable', address='Road', city='Cairo', asking_rent=500)
        response = self.client.post(f'/properties/{prop.pk}/edit/', {'name': 'Updated', 'address': 'New Road', 'city': 'Giza', 'kind': 'studio', 'bedrooms': 0, 'area': 40, 'asking_rent': 700})
        self.assertEqual(response.status_code, 302)
        prop.refresh_from_db()
        self.assertEqual(prop.name, 'Updated')
        self.assertEqual(self.client.get(f'/properties/{prop.pk}/delete/').status_code, 200)
        self.assertTrue(Property.objects.filter(pk=prop.pk).exists())
        self.client.post(f'/properties/{prop.pk}/delete/')
        self.assertFalse(Property.objects.filter(pk=prop.pk).exists())

    def test_tenant_create_edit_and_delete(self):
        response = self.client.post('/tenants/add/', {'name': 'New Tenant', 'email': 'new@example.com', 'phone': '123'})
        self.assertEqual(response.status_code, 302)
        tenant = Tenant.objects.get(name='New Tenant')
        self.client.post(f'/tenants/{tenant.pk}/edit/', {'name': 'Edited Tenant', 'email': 'new@example.com', 'phone': '456'})
        tenant.refresh_from_db()
        self.assertEqual(tenant.phone, '456')
        self.client.post(f'/tenants/{tenant.pk}/delete/')
        self.assertFalse(Tenant.objects.filter(pk=tenant.pk).exists())

    def test_cross_owner_lease_rejected(self):
        lease = Lease(property=self.prop, tenant=self.foreign_tenant, start_date=shift_month(self.month, 4), end_date=shift_month(self.month, 5), monthly_rent=1000)
        with self.assertRaises(ValidationError):
            lease.full_clean()

    def test_forged_relation_rejected_in_forms(self):
        form = LeaseForm(data={'property': self.foreign_prop.pk, 'tenant': self.tenant.pk, 'start_date': self.month, 'end_date': shift_month(self.month, 1), 'monthly_rent': 1000}, user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn('property', form.errors)
        form = PaymentForm(data={'lease': self.foreign_lease.pk, 'rent_month': self.month, 'amount': 100, 'paid_on': timezone.localdate(), 'method': 'cash'}, user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn('lease', form.errors)

    def test_overlapping_lease_rejected_including_boundary(self):
        for start in (self.month, self.lease.end_date):
            lease = Lease(property=self.prop, tenant=self.tenant, start_date=start, end_date=shift_month(self.month, 5), monthly_rent=1000)
            with self.subTest(start=start), self.assertRaises(ValidationError):
                lease.full_clean()

    def test_non_overlapping_lease_allowed(self):
        lease = Lease(property=self.prop, tenant=self.tenant, start_date=self.lease.end_date + timedelta(days=1), end_date=shift_month(self.month, 6), monthly_rent=1000)
        lease.full_clean()

    def test_lease_date_order_and_positive_rent(self):
        for end, rent in ((self.lease.start_date, 1000), (self.lease.end_date, 0)):
            self.lease.end_date, self.lease.monthly_rent = end, rent
            with self.assertRaises(ValidationError):
                self.lease.full_clean()

    def test_partial_payments_and_overpayment(self):
        self.payment(400)
        self.payment(600)
        with self.assertRaises(ValidationError):
            self.payment(1)
        self.assertEqual(Payment.objects.filter(lease=self.lease).count(), 2)

    def test_payment_edit_excludes_own_amount(self):
        payment = self.payment(400)
        payment.amount = 1000
        payment.full_clean()
        payment.save()
        self.assertEqual(rent_ledger([self.lease], self.month)[0]['status'], 'Paid')

    def test_payment_normalizes_month_and_rejects_outside_lease(self):
        payment = self.payment(rent_month=self.month.replace(day=20))
        self.assertEqual(payment.rent_month, self.month)
        with self.assertRaises(ValidationError):
            self.payment(rent_month=shift_month(self.month, -4))

    def test_negative_zero_and_future_payments_rejected(self):
        for amount in (-1, 0):
            with self.assertRaises(ValidationError):
                self.payment(amount)
        with self.assertRaises(ValidationError):
            self.payment(paid_on=timezone.localdate() + timedelta(days=1))

    def test_paid_history_cannot_be_invalidated(self):
        self.payment(1000)
        self.lease.monthly_rent = 900
        with self.assertRaises(ValidationError):
            self.lease.full_clean()
        self.lease.monthly_rent = 1000
        self.lease.start_date = shift_month(self.month, 1)
        with self.assertRaises(ValidationError):
            self.lease.full_clean()

    def test_protected_delete_retains_records(self):
        response = self.client.post(f'/properties/{self.prop.pk}/delete/', follow=True)
        self.assertContains(response, 'linked leases or payments')
        self.assertTrue(Property.objects.filter(pk=self.prop.pk).exists())
        self.payment()
        with self.assertRaises(ProtectedError):
            self.lease.delete()

    def test_payment_create_edit_delete_workflow(self):
        data = {'lease': self.lease.pk, 'rent_month': self.month.isoformat(), 'amount': '400', 'paid_on': timezone.localdate().isoformat(), 'method': 'bank'}
        self.assertEqual(self.client.post('/payments/add/', data).status_code, 302)
        payment = Payment.objects.get(lease=self.lease)
        data['amount'] = '700'
        self.assertEqual(self.client.post(f'/payments/{payment.pk}/edit/', data).status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.amount, 700)
        self.client.post(f'/payments/{payment.pk}/delete/')
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())

    def test_lease_create_edit_delete_workflow(self):
        prop = Property.objects.create(owner=self.owner, name='Another', address='Street', city='Cairo', asking_rent=500)
        data = {'property': prop.pk, 'tenant': self.tenant.pk, 'start_date': self.month.isoformat(), 'end_date': shift_month(self.month, 1).isoformat(), 'monthly_rent': '500'}
        self.assertEqual(self.client.post('/leases/add/', data).status_code, 302)
        lease = Lease.objects.get(property=prop)
        data['monthly_rent'] = '550'
        self.assertEqual(self.client.post(f'/leases/{lease.pk}/edit/', data).status_code, 302)
        lease.refresh_from_db()
        self.assertEqual(lease.monthly_rent, 550)
        self.client.post(f'/leases/{lease.pk}/delete/')
        self.assertFalse(Lease.objects.filter(pk=lease.pk).exists())

    def test_search_filters_and_invalid_month(self):
        self.assertContains(self.client.get('/properties/?q=Garden'), 'Garden House')
        self.assertNotContains(self.client.get('/properties/?q=Missing'), 'Garden House')
        self.assertContains(self.client.get('/properties/?status=occupied'), 'Garden House')
        self.assertNotContains(self.client.get('/properties/?status=vacant'), 'Garden House')
        self.assertEqual(self.client.get('/rent-roll/?month=not-a-date').status_code, 200)
        self.assertEqual(self.client.get('/payments/add/?lease=invalid').status_code, 200)
        self.assertEqual(self.client.get('/unknown/').status_code, 404)

    def test_csv_export_and_formula_safety(self):
        self.prop.name = '=DANGEROUS()'
        self.prop.save()
        self.payment(reference='@formula')
        response = self.client.get('/payments/export/')
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertContains(response, "'=DANGEROUS()")
        self.assertContains(response, "'@formula")

    def test_csrf_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(f'/properties/{self.prop.pk}/delete/').status_code, 403)

    def test_empty_portfolio(self):
        empty_user = get_user_model().objects.create_user('empty')
        self.client.force_login(empty_user)
        self.assertContains(self.client.get('/'), 'Your portfolio starts here')
        self.assertContains(self.client.get('/properties/'), 'A fresh start')

    def test_dashboard_metrics(self):
        self.payment(400)
        response = self.client.get('/')
        self.assertEqual(response.context['property_count'], 1)
        self.assertEqual(response.context['occupancy'], 100)
        self.assertEqual(response.context['outstanding'], Decimal('600'))
        self.assertEqual(response.context['collection_rate'], 40)

    def test_month_shift_and_ledger_statuses(self):
        self.assertEqual(shift_month(date(2026, 1, 1), -1), date(2025, 12, 1))
        self.assertEqual(rent_ledger([self.lease], self.month, today=self.month)[0]['status'], 'Due today')
        self.assertEqual(rent_ledger([self.lease], self.month, today=self.month + timedelta(days=1))[0]['status'], 'Overdue')
        self.payment(300)
        self.assertEqual(rent_ledger([self.lease], self.month)[0]['status'], 'Partial')
        future = shift_month(self.month, 1)
        self.assertEqual(rent_ledger([self.lease], future, today=self.month)[0]['status'], 'Upcoming')

    def test_seed_demo_is_repeatable(self):
        output = StringIO()
        call_command('seed_demo', stdout=output)
        counts = (Property.objects.count(), Payment.objects.count())
        call_command('seed_demo', stdout=output)
        self.assertEqual((Property.objects.count(), Payment.objects.count()), counts)
        self.assertIn('Nothing was changed', output.getvalue())
