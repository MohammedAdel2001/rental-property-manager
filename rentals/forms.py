from django import forms
from .models import Property, Tenant, Lease, Payment

class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['rows'] = 3
            if isinstance(field, forms.DateField):
                field.widget = forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'})
        if user:
            if 'property' in self.fields:
                self.fields['property'].queryset = Property.objects.filter(owner=user)
                self.fields['tenant'].queryset = Tenant.objects.filter(owner=user)
            if 'lease' in self.fields:
                self.fields['lease'].queryset = Lease.objects.filter(property__owner=user).select_related('property', 'tenant')

class PropertyForm(StyledModelForm):
    class Meta:
        model = Property
        fields = ['name', 'kind', 'address', 'city', 'bedrooms', 'area', 'asking_rent', 'notes']

class TenantForm(StyledModelForm):
    class Meta:
        model = Tenant
        fields = ['name', 'email', 'phone', 'notes']

class LeaseForm(StyledModelForm):
    class Meta:
        model = Lease
        fields = ['property', 'tenant', 'start_date', 'end_date', 'monthly_rent', 'notes']

class PaymentForm(StyledModelForm):
    class Meta:
        model = Payment
        fields = ['lease', 'rent_month', 'amount', 'paid_on', 'method', 'reference', 'notes']
