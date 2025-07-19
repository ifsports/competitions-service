from http.client import HTTPException

from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404

from competitions.auth.auth_utils import has_role
from competitions.models import Modality, Campus
from competitions.api.v1.serializers import ModalitySerializer

class ModalityAPIView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]
    
    def get(self, request, campus_code):
        """
        Retorna todas as modalidades para um campus específico.
        """
        campus = get_object_or_404(Campus, code=campus_code)
        modalities = Modality.objects.filter(campus=campus)

        if not modalities.exists():
            return Response({"message": "No modalities found for this campus."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ModalitySerializer(modalities, many=True)
        
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def post(self, request, campus_code):
        """
        Cria uma nova modalidade.
        """
        groups = request.user.groups

        campus = get_object_or_404(Campus, code=campus_code)

        if has_role(groups, "Organizador"):
            serializer = ModalitySerializer(data=request.data, context={'campus': campus})
            if serializer.is_valid():
                modality = serializer.save()
                return Response(ModalitySerializer(modality).data, status=status.HTTP_201_CREATED)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied("Você não tem permissão para criar uma modalidade.")

class ModalityRetrieveUpdateDestroyAPIView(APIView):
    def get_permissions(self):
        if self.request.method in ['PUT', 'DELETE']:
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, campus_code, modality_id):
        """
        Retorna uma modalidade específica para um campus específico.
        """
        campus = get_object_or_404(Campus, code=campus_code)
        modality = get_object_or_404(Modality, id=modality_id, campus=campus)
        serializer = ModalitySerializer(modality)

        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, campus_code, modality_id):
        """
        Atualiza uma modalidade específica para um campus específico.
        """
        groups = request.user.groups

        campus = get_object_or_404(Campus, code=campus_code)
        modality = get_object_or_404(Modality, id=modality_id, campus=campus)

        if has_role(groups, "Organizador"):
            serializer = ModalitySerializer(modality, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied("Você não tem permissão para atualizar uma modalidade.")

    def delete(self, request, campus_code, modality_id):
        """
        Deleta uma modalidade específica para um campus específico.
        """
        groups = request.user.groups

        campus = get_object_or_404(Campus, code=campus_code)
        modality = get_object_or_404(Modality, id=modality_id, campus=campus)

        if has_role(groups, "Organizador"):
            modality.delete()
            return Response({"message": "Modality deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

        else:
            raise PermissionDenied("Você não tem permissão para deletar uma modalidade.")