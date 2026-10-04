from django.conf import settings
from django.utils import timezone
def app_settings(request):
    return {'currency': settings.CURRENCY, 'today': timezone.localdate()}
