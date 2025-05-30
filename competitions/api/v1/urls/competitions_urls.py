from django.urls import path, include
from competitions.api.v1.views.competitions_views import (
    CompetitionRetrieveUpdateDestroyAPIView,
    CompetitionSetInProgress,
    CompetitionSetFinished,
    CompetitionTeamsAPIView,
    CompetitionTeamRetrieveUpdateDestroyAPIView,
    GenerateCompetitionsAPIView,
    CompetitionRoundsAPIView,
    CompetitionRoundMatchesAPIView,
    RoundMatchesAPIView,
    CompetitionMatchesAPIView,
    CompetitionStandingsAPIView
)

app_name = 'competitions'

urlpatterns = [
    path('<uuid:competition_id>/', CompetitionRetrieveUpdateDestroyAPIView.as_view(), name='retrieve_update_destroy'),
    path('<uuid:competition_id>/start/', CompetitionSetInProgress.as_view(), name='start'),
    path('<uuid:competition_id>/finish/', CompetitionSetFinished.as_view(), name='finish'),
    path('<uuid:competition_id>/teams/', CompetitionTeamsAPIView.as_view(), name='teams_list_and_create'),
    path('teams/<uuid:team_id>/', CompetitionTeamRetrieveUpdateDestroyAPIView.as_view(), name='teams_retrieve_update_destroy'),
    path('<uuid:competition_id>/generate/', GenerateCompetitionsAPIView.as_view(), name='generate'),
    path('<uuid:competition_id>/rounds/', CompetitionRoundsAPIView.as_view(), name='rounds_list'),
    path('<uuid:competition_id>/rounds/matches', CompetitionRoundMatchesAPIView.as_view(), name='round_matches_list'),
    path('rounds/<uuid:round_id>/matches', RoundMatchesAPIView.as_view(), name='round_matches_retrieve_update_destroy'),
    path('<uuid:competition_id>/rounds/', CompetitionRoundsAPIView.as_view(), name='rounds_list'),
    path('<uuid:competition_id>/matches/', CompetitionMatchesAPIView.as_view(), name='matches_list'),
    path('<uuid:competition_id>/standings/', CompetitionStandingsAPIView.as_view(), name='standings'),
    path('matches/', include('competitions.api.v1.urls.matches_urls')),
]
