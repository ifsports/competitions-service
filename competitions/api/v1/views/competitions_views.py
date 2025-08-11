from datetime import datetime

from rest_framework.exceptions import PermissionDenied, AuthenticationFailed, ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from rest_framework.pagination import PageNumberPagination

from jose import jwt, JWTError

from competitions.auth.auth_utils import has_role
from competitions.models import (
    Competition, CompetitionTeam, Round, Match, Modality
)

from competitions.api.v1.services.league_services.league_services import get_competition_standings, generate_league_competition, finish_match
from competitions.api.v1.services.group_elimination_services.generate_groups_elimination import generate_groups_elimination_competition
from competitions.api.v1.services.elimination_services.genarate_eliminations import generate_elimination_only_competition
from competitions.api.v1.services.group_elimination_services.generate_eliminations import assign_teams_to_knockout_stage

from competitions.api.v1.serializers import (
    CompetitionSerializer, CompetitionTeamSerializer, RoundSerializer, RoundMatchesSerializer, MatchSerializer,
    ClassificationSerializer, CompetitionTeamsInfoSerializer
)

from competitions.api.v1.messaging.publishers import generate_log_payload
from competitions.api.v1.messaging.utils import run_async_audit

import os

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse


SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
ALGORITHM = "HS256"


class CompetitionsAPIView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    @extend_schema(
        tags=["Competições"],
        summary="Lista todas as competições de um campus",
        description="""
Retorna uma lista de todas as competições associadas a um campus específico.

**Exemplo de Resposta:**

.. code-block:: json

   [
     {
       "id": "c1d2e3f4-a5b6-7890-1234-567890abcdef",
       "name": "JIFs 2025 - Futsal Masculino",
       "modality": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
       "status": "not-started",
       "start_date": "2025-09-01",
       "end_date": "2025-09-15",
       "system": "league",
       "image": "/media/competitions/futsal.jpg",
       "min_members_per_team": 5,
       "max_members_per_team": 10,
       "teams_per_group": null,
       "teams_qualified_per_group": null
     }
   ]
""",
        parameters=[
            OpenApiParameter(
                name='campus_code', description='Código do campus para filtrar as competições.', required=True, type=str)
        ],
        responses={200: CompetitionSerializer(many=True)}
    )
    def get(self, request):
        """
        Retorna todas as competições para um campus específico.
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

        competitions = Competition.objects.filter(modality__campus=campus_code)

        serializer = CompetitionSerializer(competitions, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Competições"],
        summary="Cria uma nova competição",
        description="""
Cria uma nova competição. Apenas usuários com o papel 'Organizador' podem executar esta ação.

**Exemplo de Corpo da Requisição (Payload):**

.. code-block:: json

   {
     "name": "JIFs 2025 - Voleibol Feminino",
     "modality": "b2c3d4e5-f6a7-8901-2345-67890abcdef1",
     "start_date": "2025-10-01",
     "end_date": "2025-10-10",
     "system": "elimination",
     "min_members_per_team": 6,
     "max_members_per_team": 12
   }
""",
        request=CompetitionSerializer,
        responses={201: CompetitionSerializer, 400: OpenApiResponse(
            description="Dados inválidos."), 403: OpenApiResponse(description="Permissão negada.")}
    )
    def post(self, request):
        """
        Cria uma nova competição.
        """
        groups = request.user.groups
        campus_code = request.user.campus

        if has_role(groups, "Organizador"):
            serializer = CompetitionSerializer(data=request.data)

            if serializer.is_valid():
                modality_id = request.data.get("modality")

                modality = get_object_or_404(Modality, id=modality_id)

                if modality.campus != campus_code:
                    raise ValidationError(
                        detail="Você não pode criar uma competição nessa modalidade.")

                name = serializer.validated_data["name"]
                competition_name_exists = Competition.objects.filter(
                    name=name).exists()

                if competition_name_exists:
                    raise ValidationError(
                        detail="Já existe uma competição com esse nome.")

                competition = serializer.save()

                # Publica log de auditoria (competition.created)
                log_payload = generate_log_payload(
                    event_type="competition.created",
                    service_origin="competitions_service",
                    entity_type="competition",
                    entity_id=competition.id,
                    operation_type="CREATE",
                    campus_code=campus_code,
                    user_registration=request.user.matricula,
                    request_object=request,
                    new_data=serializer.data
                )

                run_async_audit(log_payload)

                return Response(CompetitionSerializer(competition).data, status=status.HTTP_201_CREATED)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            raise PermissionDenied(
                "Você não tem permissão para criar uma competição.")


class CompetitionRetrieveUpdateDestroyAPIView(APIView):
    def get_permissions(self):
        if self.request.method in ['PUT', 'DELETE']:
            return [IsAuthenticated()]
        return [AllowAny()]

    @extend_schema(
        tags=["Competições"],
        summary="Obtém detalhes de uma competição",
        description="""
Retorna uma competição específica.

**Exemplo de Resposta:**

.. code-block:: json

   {
     "id": "c1d2e3f4-a5b6-7890-1234-567890abcdef",
     "name": "JIFs 2025 - Futsal Masculino",
     "modality": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
     "status": "not-started",
     "start_date": "2025-09-01",
     "end_date": "2025-09-15",
     "system": "league",
     "image": "/media/competitions/futsal.jpg",
     "min_members_per_team": 5,
     "max_members_per_team": 10,
     "teams_per_group": null,
     "teams_qualified_per_group": null
   }
""",
        responses={200: CompetitionSerializer, 404: OpenApiResponse(
            description="Competição não encontrada.")}
    )
    def get(self, request, competition_id):
        """
        Retorna uma competição específica.
        """

        competition = get_object_or_404(Competition, id=competition_id)

        serializer = CompetitionSerializer(competition)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Competições"],
        summary="Atualiza uma competição (parcial)",
        description="Permite a atualização de um ou mais campos de uma competição.",
        request=CompetitionSerializer,
        responses={200: CompetitionSerializer, 400: OpenApiResponse(description="Dados inválidos."), 403: OpenApiResponse(
            description="Permissão negada."), 404: OpenApiResponse(description="Competição não encontrada.")}
    )
    def put(self, request, competition_id):
        """
        Atualiza uma competição específica.
        """
        groups = request.user.groups

        competition = get_object_or_404(Competition, id=competition_id)

        if has_role(groups, "Organizador"):
            serializer = CompetitionSerializer(competition, data=request.data)

            if serializer.is_valid():
                old_competition = CompetitionSerializer(competition).data

                serializer.save()

                new_competition = serializer.data

                # Gera o payload de auditoria (competition.updated)
                log_payload = generate_log_payload(
                    event_type="competition.updated",
                    service_origin="competitions_service",
                    entity_type="competition",
                    entity_id=competition.id,
                    operation_type="UPDATE",
                    campus_code=competition.modality.campus,
                    user_registration=request.user.matricula,
                    request_object=request,
                    old_data=old_competition,
                    new_data=new_competition
                )

                # Publica o log de auditoria
                run_async_audit(log_payload)

                # Retorna a competição atualizada
                return Response(new_competition, status=status.HTTP_200_OK)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied(
                "Você não tem permissão para atualizar uma competição.")

    @extend_schema(
        tags=["Competições"],
        summary="Deleta uma competição",
        responses={204: OpenApiResponse(description="Competição deletada com sucesso."), 403: OpenApiResponse(
            description="Permissão negada."), 404: OpenApiResponse(description="Competição não encontrada.")}
    )
    def delete(self, request, competition_id):
        """
        Deleta uma competição específica.
        """
        groups = request.user.groups

        competition = get_object_or_404(Competition, id=competition_id)

        if has_role(groups, "Organizador"):
            old_competition = CompetitionSerializer(competition).data
            competition.delete()

            # Gera o payload de auditoria (competition.deleted)
            log_payload = generate_log_payload(
                event_type="competition.deleted",
                service_origin="competitions_service",
                entity_type="competition",
                entity_id=competition.id,
                operation_type="DELETE",
                campus_code=competition.modality.campus,
                user_registration=request.user.matricula,
                request_object=request,
                old_data=old_competition
            )

            # Publica o log de auditoria
            run_async_audit(log_payload)

            return Response({"message": "Competition deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

        else:
            raise PermissionDenied(
                "Você não tem permissão para deletar uma competição.")


class CompetitionSetInProgress(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Gerenciamento de Competição"],
        summary="Inicia uma competição",
        description="Altera o status de uma competição de 'não iniciada' para 'em andamento'. Esta rota não recebe corpo.",
        request=None,
        responses={200: OpenApiResponse(description="Status da competição alterado para 'em andamento'."), 400: OpenApiResponse(
            description="Competição já iniciada ou finalizada."), 403: OpenApiResponse(description="Permissão negada.")}
    )
    def patch(self, request, competition_id):
        """
        Atualiza o status de uma competição específica.
        """
        groups = request.user.groups

        competition = get_object_or_404(Competition, id=competition_id)

        if has_role(groups, "Organizador"):
            if competition.status == 'not-started':
                old_competition = competition

                competition.status = 'in-progress'
                competition.save()

                # Gera o payload de auditoria
                log_payload = generate_log_payload(
                    event_type="competition.updated",
                    service_origin="competitions_service",
                    entity_type="competition",
                    entity_id=competition.id,
                    operation_type="UPDATE",
                    campus_code=competition.modality.campus,
                    user_registration=request.user.matricula,
                    request_object=request,
                    old_data={"status": old_competition.status},
                    new_data={"status": competition.status}
                )

                # Publica o log de auditoria
                run_async_audit(log_payload)

                return Response({"message": "Competition status updated to in-progress."}, status=status.HTTP_200_OK)

            return Response({"message": "Competition is already in progress or finished."}, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied(
                "Você não tem permissão para atualizar o status de uma competição.")


class CompetitionSetFinished(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Gerenciamento de Competição"],
        summary="Finaliza uma competição",
        description="Altera o status de uma competição de 'em andamento' para 'finalizada'. Esta rota não recebe corpo.",
        request=None,
        responses={200: OpenApiResponse(description="Status da competição alterado para 'finalizada'."), 400: OpenApiResponse(
            description="Competição já finalizada ou não iniciada."), 403: OpenApiResponse(description="Permissão negada.")}
    )
    def patch(self, request, competition_id):
        """
        Atualiza o status de uma competição específica.
        """
        groups = request.user.groups

        competition = get_object_or_404(Competition, id=competition_id)

        if has_role(groups, "Organizador"):
            if competition.status == 'in-progress':
                old_competition = competition

                competition.status = 'finished'
                competition.save()

                # Gera o payload de auditoria
                log_payload = generate_log_payload(
                    event_type="competition.updated",
                    service_origin="competitions_service",
                    entity_type="competition",
                    entity_id=competition.id,
                    operation_type="UPDATE",
                    campus_code=competition.modality.campus,
                    user_registration=request.user.matricula,
                    request_object=request,
                    old_data={"status": old_competition.status},
                    new_data={"status": competition.status}
                )

                # Publica o log de auditoria
                run_async_audit(log_payload)

                return Response({"message": "Competition status updated to finished."}, status=status.HTTP_200_OK)

            return Response({"message": "Competition is already finished or is not-started."}, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied(
                "Você não tem permissão para atualizar o status de uma competição.")


class CompetitionTeamsAPIView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    @extend_schema(
        tags=["Times em Competição"],
        summary="Lista os times de uma competição",
        description="""
**Exemplo de Resposta:**

.. code-block:: json

   [
     {
       "team_id": "d1e2f3a4-b5c6-7890-1234-567890abcdef",
       "competition": { "...dados da competição..." }
     }
   ]
""",
        responses={200: CompetitionTeamSerializer(many=True)}
    )
    def get(self, request, competition_id):
        """
        Retorna todas as equipes de uma competição específica.
        """

        competition = get_object_or_404(Competition, id=competition_id)

        teams = CompetitionTeam.objects.filter(competition=competition)

        serializer = CompetitionTeamSerializer(teams, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Times em Competição"],
        summary="Inscreve um time em uma competição",
        description="""
Verifica se um time já está inscrito e, caso não esteja, realiza a inscrição.

**Exemplo de Corpo da Requisição (Payload):**

.. code-block:: json

   {
     "team_id": "d1e2f3a4-b5c6-7890-1234-567890abcdef"
   }
""",
        request={'application/json': {'example': {'team_id': 'uuid-do-time'}}},
        responses={201: CompetitionTeamSerializer, 409: OpenApiResponse(
            description="O time já está inscrito.")}
    )
    def post(self, request, competition_id):
        """"
        Verifica existencia de uma equipe para uma competição específica.
        """
        groups = request.user.groups

        competition = get_object_or_404(Competition, id=competition_id)

        team_id_from_request = request.data.get('team_id')
        if not team_id_from_request:
            return Response(
                {"message": "O campo 'team_id' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if has_role(groups, "Organizador", "Jogador"):
            team_exists = CompetitionTeam.objects.filter(
                team_id=team_id_from_request, competition=competition).exists()

            if team_exists:
                return Response({
                    "can_be_inscribed": False,
                    "message": "A equipe já está inscrita nesta competição."
                }, status=status.HTTP_409_CONFLICT)

            else:
                serializer = CompetitionTeamsInfoSerializer(competition)

                return Response({
                    "can_be_inscribed": True,
                    "message": "A equipe pode ser inscrita nesta competição.",
                    "data": serializer.data,
                }, status=status.HTTP_200_OK)

        else:
            raise PermissionDenied(
                "Você não tem permissão para verificar a existencia de uma equipe em uma competição")


class GenerateCompetitionsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Gerenciamento de Competição"],
        summary="Gera as fases e partidas da competição",
        description="Este endpoint aciona a lógica de criação de grupos, rodadas e partidas com base no sistema da competição (pontos corridos, eliminatórias, etc.). Não recebe corpo na requisição.",
        request=None,
        responses={201: OpenApiResponse(description="Competição gerada com sucesso."), 400: OpenApiResponse(
            description="Erro na lógica de geração (ex: número de times insuficiente).")}
    )
    def post(self, request, competition_id):
        """
        Gera os jogos e classificações de uma competição específica.
        """
        groups = request.user.groups

        competition = get_object_or_404(Competition, id=competition_id)

        if has_role(groups, "Organizador"):
            if competition.system == 'league':
                try:
                    generate_league_competition(competition)
                    return Response({"message": "League competition generated successfully."}, status=status.HTTP_201_CREATED)
                except ValueError as e:
                    return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            elif competition.system == 'groups_elimination':
                try:
                    generate_groups_elimination_competition(competition)
                    return Response({"message": "Groups competition generated successfully."}, status=status.HTTP_201_CREATED)
                except ValueError as e:
                    return Response(
                        {"error":  str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            elif competition.system == 'elimination':
                try:
                    generate_elimination_only_competition(competition)
                    return Response({'message': 'Elimination competition generated succesfully.'}, status=status.HTTP_201_CREATED)
                except ValueError as e:
                    return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied(
                "Você não tem permissão para gerar uma competição.")


class EndGroupStageAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Gerenciamento de Competição"],
        summary="Finaliza a fase de grupos",
        description="Calcula os classificados da fase de grupos e gera as partidas da fase eliminatória (oitavas, quartas, etc.). Não recebe corpo na requisição.",
        request=None,
        responses={200: OpenApiResponse(description="Fase eliminatória gerada com sucesso."), 400: OpenApiResponse(
            description="Erro na lógica ou competição não está no sistema correto.")}
    )
    def post(self, request, competition_id):
        """
        Finaliza a fase de grupos e gera fase eliminatorias de uma competição específica.
        """
        groups = request.user.groups

        competition = get_object_or_404(Competition, id=competition_id)

        if has_role(groups, "Organizador"):
            if competition.system == 'groups_elimination':
                try:
                    assign_teams_to_knockout_stage(competition)
                    return Response({"message": "Teams assigned to knockout stage successfully."}, status=status.HTTP_200_OK)
                except ValueError as e:
                    return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(
                    {"error": "This endpoint is only for competitions with 'groups_elimination' system."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        else:
            raise PermissionDenied(
                "Você não tem permissão para finalizar a fase de grupos de uma competição.")


class CompetitionTeamRetrieveUpdateDestroyAPIView(APIView):
    """
    View para ver, atualizar e deletar a inscrição de um Time específico em uma competição.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Times em Competição"],
        summary="Obtém detalhes da inscrição de um time",
        responses={200: CompetitionTeamSerializer, 403: OpenApiResponse(
            description="Permissão negada."), 404: OpenApiResponse(description="Inscrição de time não encontrada.")}
    )
    def get(self, request, team_id):
        """
        Retorna uma equipe específica de uma competição específica.
        """
        groups = request.user.groups

        team = get_object_or_404(CompetitionTeam, team_id=team_id)

        if has_role(groups, "Organizador", "Jogador"):
            serializer = CompetitionTeamSerializer(team)
            return Response(serializer.data, status=status.HTTP_200_OK)

        else:
            raise PermissionDenied(
                "Você não tem permissão para listar detalhes de uma equipe.")

    @extend_schema(
        tags=["Times em Competição"],
        summary="Atualiza a inscrição de um time (uso futuro)",
        request=CompetitionTeamSerializer,
        responses={200: CompetitionTeamSerializer, 400: OpenApiResponse(
            description="Dados inválidos."), 403: OpenApiResponse(description="Permissão negada.")}
    )
    def put(self, request, team_id):
        """
        Atualiza uma equipe específica de uma competição específica.
        """
        groups = request.user.groups

        team = get_object_or_404(CompetitionTeam, team_id=team_id)

        if has_role(groups, "Organizador"):
            serializer = CompetitionTeamSerializer(
                team, data=request.data, partial=True)

            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied(
                "Você não tem permissão para atualizar uma equipe.")

    @extend_schema(
        tags=["Times em Competição"],
        summary="Remove um time de uma competição",
        responses={204: OpenApiResponse(description="Time removido com sucesso."), 403: OpenApiResponse(
            description="Permissão negada.")}
    )
    def delete(self, request, team_id):
        """
        Deleta uma equipe específica de uma competição específica.
        """
        groups = request.user.groups

        team = get_object_or_404(CompetitionTeam, team_id=team_id)

        if has_role(groups, "Organizador"):
            team.delete()
            return Response({"message": "Team deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

        else:
            raise PermissionDenied(
                "Você não tem permissão para deletar uma equipe.")


class CompetitionRoundsAPIView(APIView):
    """
    Lista as rodadas de uma competição.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Rodadas e Partidas"],
        summary="Lista as rodadas de uma competição",
        description="Retorna todas as rodadas de uma competição específica.",
        responses={200: RoundSerializer(many=True)}
    )
    def get(self, request, competition_id):
        """
        Retorna todas as rodadas de uma competição específica.
        """

        competition = get_object_or_404(Competition, id=competition_id)

        rounds = Round.objects.filter(
            match__competition=competition).distinct()

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(rounds, request, view=self)

        serializer = RoundSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class CompetitionRoundMatchesAPIView(APIView):
    """
    Lista as rodadas de uma competição, incluindo as partidas de cada rodada.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Rodadas e Partidas"],
        summary="Lista rodadas com suas respectivas partidas",
        description="Retorna todas as rodadas de uma competição específica, com as informações das partidas aninhadas.",
        responses={200: RoundMatchesSerializer(many=True)}
    )
    def get(self, request, competition_id):
        """
        Retorna todas as rodadas de uma competição específica.
        """
        competition = get_object_or_404(Competition, id=competition_id)

        rounds_queryset = Round.objects.filter(
            match__competition=competition
        ).prefetch_related(
            Prefetch(
                'match_set',
                queryset=Match.objects.select_related(
                    'team_home',
                    'team_away',
                    'competition',
                    'group',
                    'round'
                )
            )
        ).distinct()

        paginator = PageNumberPagination()

        page = paginator.paginate_queryset(rounds_queryset, request, view=self)

        serializer = RoundMatchesSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class CompetitionMatchesAPIView(APIView):
    """
    Lista todas as partidas de uma única competição.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Rodadas e Partidas"],
        summary="Lista todas as partidas de uma competição",
        description="Retorna todas as partidas de uma competição específica.",
        responses={200: MatchSerializer(many=True)}
    )
    def get(self, request, competition_id):
        """
        Retorna todas as partidas de uma competição específica.
        """

        competition = get_object_or_404(Competition, id=competition_id)

        matches_queryset = Match.objects.filter(competition=competition).select_related(
            'team_home__competition',
            'team_away__competition',
            'group',
            'round',
            'winner'
        )

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(
            matches_queryset, request, view=self)

        serializer = MatchSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class RoundMatchesAPIView(APIView):
    """
    Lista todas as partidas de uma única rodada.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Rodadas e Partidas"],
        summary="Lista as partidas de uma rodada específica",
        description="Retorna todos os jogos de uma rodada específica.",
        responses={200: MatchSerializer(many=True)}
    )
    def get(self, request, round_id):
        """
        Retorna todos os jogos de uma rodada específica
        """

        round = Round.objects.filter(id=round_id).prefetch_related(
            Prefetch('match_set', queryset=Match.objects.select_related(
                'team_home',
                'team_away',
                'group',
                'round',
                'competition'
            ))).distinct().first()

        matches = round.match_set.all()

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(matches, request, view=self)

        serializer = MatchSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class MatchesAPIView(APIView):
    """
    Retorna todas as partidas de todas as competições de um campus específico.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Partidas"],
        summary="Lista todas as partidas de um campus",
        description="Retorna todas as partidas de todas as competições de um campus específico.",
        parameters=[
            OpenApiParameter(
                name='campus_code', description='Código do campus para filtrar as partidas.', required=True, type=str)
        ],
        responses={200: MatchSerializer(many=True)}
    )
    def get(self, request):
        """
        Retorna todas as partidas de todas as competições de um campus específico.
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

        competitions = Competition.objects.filter(modality__campus=campus_code)

        matches = Match.objects.filter(competition__in=competitions).all()

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(matches, request, view=self)

        serializer = MatchSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class MatchesTodayAPIView(APIView):
    """
    Lista as partidas que acontecem hoje.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Partidas"],
        summary="Lista as partidas de hoje",
        description="Pode ser filtrada por `campus_code` (para ver todos os jogos do dia no campus) ou por `competition_id` (para ver os jogos do dia em uma competição específica).",
        parameters=[
            OpenApiParameter(
                name='campus_code', description='(Opcional) Filtra as partidas pelo campus.', type=str),
            OpenApiParameter(
                name='competition_id', description='(Opcional) Filtra as partidas pela competição.', type=str)
        ],
        responses={200: MatchSerializer(many=True)}
    )
    def get(self, request, competition_id=None):
        campus_code = request.query_params.get('campus_code')
        today = datetime.now().date()

        if campus_code:
            matches_queryset = Match.objects.filter(
                competition__modality__campus=campus_code,
                scheduled_datetime__date=today
            )
        else:
            competition = get_object_or_404(Competition, id=competition_id)
            matches_queryset = Match.objects.filter(
                competition=competition,
                scheduled_datetime__date=today
            )

        serializer = MatchSerializer(matches_queryset, many=True)
        return Response(serializer.data)


class MatchRetrieveUpdateAPIView(APIView):
    """
    View para ver ou atualizar uma Partida específica.
    """

    def get_permissions(self):
        if self.request.method == 'PUT':
            return [IsAuthenticated()]
        return [AllowAny()]

    @extend_schema(
        tags=["Partidas"],
        summary="Obtém detalhes de uma partida",
        description="Retorna uma partida específica de uma competição.",
        responses={200: MatchSerializer}
    )
    def get(self, request, match_id):
        """
        Retorna uma partida específica de uma competição.
        """
        match = get_object_or_404(Match, id=match_id)

        serializer = MatchSerializer(match)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Partidas"],
        summary="Atualiza dados de uma partida",
        description="Permite atualizar informações como placar, data, etc. Apenas para Organizadores.",
        request=MatchSerializer,
        responses={200: MatchSerializer}
    )
    def put(self, request, match_id):
        """
        Atualiza uma partida específica de uma competição.
        """
        groups = request.user.groups

        match = get_object_or_404(Match, id=match_id)

        if has_role(groups, "Organizador"):
            serializer = MatchSerializer(
                match, data=request.data, partial=True)

            if serializer.is_valid():
                old_data = MatchSerializer(match).data
                match = serializer.save()
                new_data = MatchSerializer(match).data

                # Gera o payload de auditoria (match.updated)
                log_payload = generate_log_payload(
                    event_type="match.updated",
                    service_origin="competitions_service",
                    entity_type="match",
                    entity_id=match.id,
                    operation_type="UPDATE",
                    campus_code=match.competition.modality.campus,
                    user_registration=request.user.matricula,
                    request_object=request,
                    old_data=old_data,
                    new_data=new_data
                )

                # Publica o log de auditoria
                run_async_audit(log_payload)

                return Response(MatchSerializer(match).data, status=status.HTTP_200_OK)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied(
                "Você não tem permissão para atualizar uma partida de uma competição")


class MatchStartAPIView(APIView):
    """
    Altera o status de uma partida para "em andamento".
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Gerenciamento de Partidas"],
        summary="Inicia uma partida",
        description="Altera o status de uma partida para 'em andamento'. Não recebe corpo na requisição.",
        request=None,
        responses={200: OpenApiResponse(
            description="Status da partida alterado para 'em andamento'.")}
    )
    def patch(self, request, match_id):
        """
        Atualiza o satus de uma partida específica de uma competição para "em andamento".
        """
        groups = request.user.groups

        match = get_object_or_404(Match, id=match_id)

        if has_role(groups, "Organizador"):
            if match.status == 'not-started':
                old_data = MatchSerializer(match).data
                match.status = 'in-progress'
                match.save()
                new_data = MatchSerializer(match).data

                # Gera o payload de auditoria (match.updated)
                log_payload = generate_log_payload(
                    event_type="match.updated",
                    service_origin="competitions_service",
                    entity_type="match",
                    entity_id=match.id,
                    operation_type="UPDATE",
                    campus_code=match.competition.modality.campus,
                    user_registration=request.user.matricula,
                    request_object=request,
                    old_data=old_data,
                    new_data=new_data
                )

                # Publica o log de auditoria
                run_async_audit(log_payload)

                return Response({"message": "Match status updated to in-progress."}, status=status.HTTP_200_OK)

            return Response({"message": "Match is already in progress or finished."}, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied(
                "Você não tem permissão para atualizar o status da partida de uma competição")


class MatchFinishAPIView(APIView):
    """
    Altera o status de uma partida para "finalizada" e atualiza o placar.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Gerenciamento de Partidas"],
        summary="Finaliza uma partida",
        description="""
Atualiza o status de uma partida para "finalizada" e registra o placar final.

**Exemplo de Corpo da Requisição (Payload):**

.. code-block:: json

   {
     "score_home": 3,
     "score_away": 2
   }
""",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'score_home': {'type': 'integer'},
                    'score_away': {'type': 'integer'}
                },
                'required': ['score_home', 'score_away']
            }
        },
        responses={200: OpenApiResponse(
            description="Partida finalizada e placar atualizado com sucesso.")}
    )
    def patch(self, request,  match_id):
        """
        Atualiza o satus de uma partida específica de uma competição para "finalizada".
        """
        groups = request.user.groups

        match = get_object_or_404(Match, id=match_id)

        if has_role(groups, "Organizador"):
            if match.status == 'in-progress':
                old_data = MatchSerializer(match).data
                finish_match(match)
                new_data = MatchSerializer(match).data

                # Gera o payload de auditoria (match.updated)
                log_payload = generate_log_payload(
                    event_type="match.updated",
                    service_origin="competitions_service",
                    entity_type="match",
                    entity_id=match.id,
                    operation_type="UPDATE",
                    campus_code=match.competition.modality.campus,
                    user_registration=request.user.matricula,
                    request_object=request,
                    old_data=old_data,
                    new_data=new_data
                )

                # Publica o log de auditoria
                run_async_audit(log_payload)

                return Response({"message": "Match data updated and finished."}, status=status.HTTP_200_OK)

            return Response({"message": "Match is already finished or not started."}, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied(
                "Você não tem permissão para atualizar o status da partida de uma competição")


class CompetitionStandingsAPIView(APIView):
    """
    Retorna a tabela de classificação ou as chaves de uma competição.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Tabelas e Classificação"],
        summary="Obtém a tabela de classificação da competição",
        description="Para competições de pontos corridos ou grupos, retorna a tabela de classificação. Para eliminatórias, retorna a árvore de partidas.",
        responses={200: ClassificationSerializer(many=True)}
    )
    def get(self, request, competition_id):
        """
        Retorna a classificação de uma competição específica.
        """

        competition = get_object_or_404(Competition, id=competition_id)

        standings = get_competition_standings(competition)

        if not standings:
            return Response({"message": "No standings found for this competition."}, status=status.HTTP_404_NOT_FOUND)

        if competition.system == 'elimination':
            # As competições de eliminatorias apenas retornam as partidas ordenadas por fase
            serializer = MatchSerializer(standings, many=True)
        else:
            serializer = ClassificationSerializer(standings, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
