import logging
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from bd_models.models import APIKey

logger = logging.getLogger(__name__)

class APIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        logger.debug("APIKeyAuthentication: Checking for API key...")
        api_key = request.headers.get('Authorization')
        if not api_key or not api_key.startswith('Api-Key '):
            logger.debug("APIKeyAuthentication: No API key found.")
            return None

        key = api_key.split(' ')[1]
        try:
            api_key_obj = APIKey.objects.get(key=key)
            logger.debug("APIKeyAuthentication: API key is valid.")
        except APIKey.DoesNotExist:
            logger.debug("APIKeyAuthentication: Invalid API key.")
            raise AuthenticationFailed('Invalid API key')

        return (api_key_obj, None)