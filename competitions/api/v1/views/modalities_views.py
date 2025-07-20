from http.client import HTTPException

from rest_framework.exceptions import PermissionDenied, AuthenticationFailed
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404

from jose import jwt, JWTError

from competitions.auth.auth_utils import has_role
from competitions.models import Modality
from competitions.api.v1.serializers import ModalitySerializer

SECRET_KEY = "django-insecure-f=td$@o*6$utz@_2kvjf$zss#*r_8f74whhgo9y#p7rz@t*ii("
ALGORITHM = "HS256"

class ModalityAPIView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]
    
    def get(self, request):
        """
        Retorna todas as modalidades para um campus específico.
        """
        campus_code = request.query_params.get("campus_code")
        groups = []

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                campus_code = payload.get("campus", campus_code)
                groups = payload.get("groups", [])
            except JWTError:
                raise AuthenticationFailed("Token inválido ou expirado.")

        if not campus_code:
            return Response(
                {"detail": "Campus não especificado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        modalities = Modality.objects.filter(campus=campus_code)

        if not modalities.exists():
            return Response({"message": "No modalities found for this campus."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ModalitySerializer(modalities, many=True)
        
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def post(self, request):
        """
        Cria uma nova modalidade.
        """
        groups = request.user.groups
        campus_code = request.user.campus

        if has_role(groups, "Organizador"):
            data_serializer = request.data.copy()
            data_serializer['campus'] = campus_code

            serializer = ModalitySerializer(data=data_serializer)

            if serializer.is_valid():
                modality = serializer.save()
                return Response(ModalitySerializer(modality).data, status=status.HTTP_201_CREATED)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied("Você não tem permissão para criar uma modalidade.")

class ModalityRetrieveUpdateDestroyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, modality_id):
        """
        Retorna uma modalidade específica para um campus específico.
        """
        groups = request.user.groups
        campus_code = request.user.campus

        modality = get_object_or_404(Modality, id=modality_id, campus=campus_code)

        if has_role(groups, "Organizador"):
            serializer = ModalitySerializer(modality)

            return Response(serializer.data, status=status.HTTP_200_OK)

        else:
            raise PermissionDenied("Você não tem permissão para listar os detalhes de uma modalidade.")
    
    def put(self, request, modality_id):
        """
        Atualiza uma modalidade específica para um campus específico.
        """
        groups = request.user.groups
        campus_code = request.user.campus

        modality = get_object_or_404(Modality, id=modality_id, campus=campus_code)

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
        campus_code = request.user.groups

        modality = get_object_or_404(Modality, id=modality_id, campus=campus_code)

        if has_role(groups, "Organizador"):
            modality.delete()
            return Response({"message": "Modality deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

        else:
            raise PermissionDenied("Você não tem permissão para deletar uma modalidade.")