from django.contrib import admin
from .models import Property, Tenant, Lease, Payment

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'kind', 'asking_rent', 'owner']
    search_fields = ['name', 'address', 'city']
    list_filter = ['kind', 'city']

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'phone', 'owner']
    search_fields = ['name', 'email']

@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = ['property', 'tenant', 'start_date', 'end_date', 'monthly_rent']
    list_select_related = ['property', 'tenant']

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['lease', 'rent_month', 'amount', 'paid_on', 'method']
    list_filter = ['method', 'rent_month']
    list_select_related = ['lease__property', 'lease__tenant']

admin.site.site_header = 'Rental Property Manager'
admin.site.site_title = 'Rental Property Manager'
admin.site.index_title = 'Administration'
