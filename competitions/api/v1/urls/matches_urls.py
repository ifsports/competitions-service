from django.urls import path

from competitions.api.v1.views.competitions_views import MatchRetrieveUpdateAPIView, MatchStartAPIView, \
    MatchFinishAPIView, MatchesTodayAPIView

app_name = 'matches'

urlpatterns = [
    path('today/', MatchesTodayAPIView.as_view(), name='match_today'),
    path('<uuid:match_id>/', MatchRetrieveUpdateAPIView.as_view(), name='match_retrieve_update'),
    path('<uuid:match_id>/start', MatchStartAPIView.as_view(), name='match_start'),
    path('<uuid:match_id>/finish', MatchFinishAPIView.as_view(), name='match_finish'),
]