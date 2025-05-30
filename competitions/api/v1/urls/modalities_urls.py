from django.urls import path
from competitions.api.v1.views.modalities_views import (
    ModalityRetrieveUpdateDestroyAPIView,
)

app_name = 'modalities'

urlpatterns = [
    path('<uuid:modality_id>/', ModalityRetrieveUpdateDestroyAPIView.as_view(), name='retrieve_update_destroy'),
]