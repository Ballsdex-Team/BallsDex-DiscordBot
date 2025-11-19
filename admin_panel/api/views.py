from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_ratelimit.decorators import ratelimit
from bd_models.models import APIKey, BallInstance
from django.utils.decorators import method_decorator


def api_key_ratelimit_key(group, request):
	return request.headers.get("Authorization", "")

class BallInstancesView(APIView):
	# permission_classes = [IsAuthenticated] #TODO: Enable authentication later


	@method_decorator(ratelimit(key=api_key_ratelimit_key, rate='5/m', method='GET', block=True), name='dispatch')
	def get(self, request) -> Response:
		api_key = request.headers.get("Authorization")
		try:
			api_key_obj = APIKey.objects.get(key=api_key)
		except APIKey.DoesNotExist:
			return Response({"error": "Invalid APIKey"}, status=403)

		player_id = api_key_obj.player
		ball_instances = BallInstance.objects.filter(player_id=player_id).all()

		data = [
			{
				"id": ball.pk,
				"ball": str(ball),
				"attack": ball.attack_bonus,
				"health": ball.health_bonus,
				"created_at": ball.catch_date,
				"catch_time": ball.catch_time(),
			}
			for ball in ball_instances
		]
		return Response(data, status=200)