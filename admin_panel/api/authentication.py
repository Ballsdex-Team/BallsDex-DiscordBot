from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from bd_models.models import APIKey

class APIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get('Authorization')
        if not api_key or not api_key.startswith('Api-Key '):
            return None

        key = api_key.split(' ')[1]
        try:
            api_key_obj = APIKey.objects.get(key=key)
        except APIKey.DoesNotExist:
            raise AuthenticationFailed('Invalid API key')

        return (api_key_obj, None)