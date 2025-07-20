from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from competitions.api.v1.views.competitions_views import CompetitionsAPIView, MatchesAPIView
from competitions.api.v1.views.modalities_views import ModalityAPIView


urlpatterns = [
    # Endpoints do drf-spectacular
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='api-schema'), name='api-docs'),
    path('api/v1/competitions/', CompetitionsAPIView.as_view(), name='competitions:list_and_create'),
    path('api/v1/competitions/',include(
        ('competitions.api.v1.urls.competitions_urls', 'competitions'),
        namespace='competitions')),
    path('api/v1/matches/', MatchesAPIView.as_view(), name='matches:list'),
    # Modalities URLS
    path('api/v1/modalities/', ModalityAPIView.as_view(), name='modalities:list_and_create'),
    path('api/v1/modalities/', include(('competitions.api.v1.urls.modalities_urls', 'modalities'),
        namespace='modalities')),
]
