from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_ratelimit.decorators import ratelimit
from bd_models.models import APIKey, BallInstance

class BallInstancesView(APIView):
	permission_classes = [IsAuthenticated]

	@ratelimit(key='ip', rate='5/m', method='GET', block=True)
	async def get(self, request) -> Response:
		api_key = request.headers.get("APIKey")
		try:
			api_key_obj = await APIKey.objects.aget(key=api_key)
		except APIKey.DoesNotExist:
			return Response({"error": "Invalid APIKey"}, status=403)

		player_id = api_key_obj.player
		ball_instances = await BallInstance.objects.filter(player_id=player_id).aall()

		data = [{"id": ball.pk, "name": ball.countryball.country} for ball in ball_instances]
		return Response(data, status=200)