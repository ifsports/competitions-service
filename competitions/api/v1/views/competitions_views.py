from rest_framework.exceptions import PermissionDenied, AuthenticationFailed
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
    Competition, Campus, CompetitionTeam, Round, Match
)

from competitions.api.v1.services.league_services.league_services import get_competition_standings, generate_league_competition, finish_match
from competitions.api.v1.services.group_elimination_services.generate_groups_elimination import generate_groups_elimination_competition
from competitions.api.v1.services.elimination_services.genarate_eliminations import generate_elimination_only_competition
from competitions.api.v1.services.group_elimination_services.generate_eliminations import assign_teams_to_knockout_stage

from competitions.api.v1.serializers import (
    CompetitionSerializer, CompetitionTeamSerializer, RoundSerializer, RoundMatchesSerializer, MatchSerializer,
    ClassificationSerializer, CompetitionTeamsInfoSerializer
)

SECRET_KEY = "django-insecure-f=td$@o*6$utz@_2kvjf$zss#*r_8f74whhgo9y#p7rz@t*ii("
ALGORITHM = "HS256"

class CompetitionsAPIView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

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

        campus = get_object_or_404(Campus, code=campus_code)
        competitions = Competition.objects.filter(modality__campus=campus)

        if not competitions.exists():
            return Response({"message": "No competitions found for this campus."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CompetitionSerializer(competitions, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def post(self, request, campus_code):
        """
        Cria uma nova competição.
        """
        groups = request.user.groups

        if has_role(groups, "Organizador"):
            serializer = CompetitionSerializer(data=request.data)

            if serializer.is_valid():
                competition = serializer.save()
                return Response(CompetitionSerializer(competition).data, status=status.HTTP_201_CREATED)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied("Você não tem permissão para criar uma competição.")

class CompetitionRetrieveUpdateDestroyAPIView(APIView):
    def get_permissions(self):
        if self.request.method in ['PUT', 'DELETE']:
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, competition_id):
        """
        Retorna uma competição específica.
        """
        
        competition = get_object_or_404(Competition, id=competition_id)

        serializer = CompetitionSerializer(competition)
        
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, competition_id):
        """
        Atualiza uma competição específica.
        """
        groups = request.user.groups

        competition = get_object_or_404(Competition, id=competition_id)

        if has_role(groups, "Organizador"):
            serializer = CompetitionSerializer(competition, data=request.data)

            if serializer.is_valid():
                competition = serializer.save()
                return Response(CompetitionSerializer(competition).data, status=status.HTTP_200_OK)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied("Você não tem permissão para atualizar uma competição.")
    
    def delete(self, request, competition_id):
        """
        Deleta uma competição específica.
        """
        groups = request.user.groups

        competition = get_object_or_404(Competition, id=competition_id)

        if has_role(groups, "Organizador"):
            competition.delete()
            return Response({"message": "Competition deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

        else:
            raise PermissionDenied("Você não tem permissão para deletar uma competição.")

class CompetitionSetInProgress(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, competition_id):
        """
        Atualiza o status de uma competição específica.
        """
        groups = request.user.groups

        competition = get_object_or_404(Competition, id=competition_id)

        if has_role(groups, "Organizador"):
            if competition.status == 'not-started':
                competition.status = 'in-progress'
                competition.save()
                return Response({"message": "Competition status updated to in-progress."}, status=status.HTTP_200_OK)

            return Response({"message": "Competition is already in progress or finished."}, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied("Você não tem permissão para atualizar o status de uma competição.")
    
class CompetitionSetFinished(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, competition_id):
        """
        Atualiza o status de uma competição específica.
        """
        groups = request.user.groups

        competition = get_object_or_404(Competition, id=competition_id)

        if has_role(groups, "Organizador"):
            if competition.status == 'in-progress':
                competition.status = 'finished'
                competition.save()
                return Response({"message": "Competition status updated to finished."}, status=status.HTTP_200_OK)

            return Response({"message": "Competition is already finished or is not-started."}, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied("Você não tem permissão para atualizar o status de uma competição.")

class CompetitionTeamsAPIView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, competition_id):
        """
        Retorna todas as equipes de uma competição específica.
        """
        
        competition = get_object_or_404(Competition, id=competition_id)

        teams = CompetitionTeam.objects.filter(competition=competition)

        if not teams.exists():
            return Response({"message": "No teams found for this competition."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = CompetitionTeamSerializer(teams, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

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
            team_exists = CompetitionTeam.objects.filter(team_id=team_id_from_request, competition=competition).exists()

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
            raise PermissionDenied("Você não tem permissão para verificar a existencia de uma equipe em uma competição")

class GenerateCompetitionsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, competition_id):
        """
        Gera equipes para uma competição específica.
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
                except:
                    return Response({'error': str(e)})

        else:
            raise PermissionDenied("Você não tem permissão para gerar equipes para uma competição.")

class EndGroupStageAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, competition_id):
        """
        Finaliza a fase de grupos de uma competição específica.
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
            raise PermissionDenied("Você não tem permissão para finalizar a fase de grupos de uma competição.")

class CompetitionTeamRetrieveUpdateDestroyAPIView(APIView):
    permission_classes = [IsAuthenticated]

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
            raise PermissionDenied("Você não tem permissão para listar detalhes de uma equipe.")
    
    def put(self, request, team_id):
        """
        Atualiza uma equipe específica de uma competição específica.
        """
        groups = request.user.groups

        team = get_object_or_404(CompetitionTeam, team_id=team_id)

        if has_role(groups, "Organizador"):
            serializer = CompetitionTeamSerializer(team, data=request.data, partial=True)

            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied("Você não tem permissão para atualizar uma equipe.")
    
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
            raise PermissionDenied("Você não tem permissão para deletar uma equipe.")

class CompetitionRoundsAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, competition_id):
        """
        Retorna todas as rodadas de uma competição específica.
        """
        
        competition = get_object_or_404(Competition, id=competition_id)

        rounds = Round.objects.filter(match__competition=competition).distinct()

        if not rounds.exists():
            return Response({"message": "No rounds found for this competition."}, status=status.HTTP_404_NOT_FOUND)

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(rounds, request, view=self)

        serializer = RoundSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
    
class CompetitionRoundMatchesAPIView(APIView):
    permission_classes = [AllowAny]

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

        if not page:
            return Response(
                {"detail": "Nenhuma rodada encontrada para esta competição."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = RoundMatchesSerializer(page, many=True)
        
        return paginator.get_paginated_response(serializer.data)
    
class CompetitionMatchesAPIView(APIView):
    permission_classes = [AllowAny]
    def get(self, request, competition_id):
        """
        Retorna todas as partidas de uma competição específica.
        """
        
        competition = get_object_or_404(Competition, id=competition_id)

        matches_queryset = Match.objects.filter(competition=competition).all()

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(matches_queryset, request, view=self)

        if not page:
            return Response({"message": "No matches found for this competition."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = MatchSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

class RoundMatchesAPIView(APIView):
    permission_classes = [AllowAny]

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
        

        if not round.exists():
            return Response({"message": "Round not found for this competition."}, status=status.HTTP_404_NOT_FOUND)

        matches = round.match_set.all()

        if not matches.exists():
            return Response({"message": "No matches found for this round."}, status=status.HTTP_404_NOT_FOUND)

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(matches, request, view=self)

        serializer = MatchSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

class MatchesAPIView(APIView):
    """
    Retorna todas as partidas de todas as competições de um campus específico.
    """
    permission_classes = [AllowAny]

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

        campus = get_object_or_404(Campus, code=campus_code)
        competitions = Competition.objects.filter(modality__campus=campus)

        if not competitions.exists():
            return Response({"message": "No competitions found for this campus."}, status=status.HTTP_404_NOT_FOUND)

        matches = Match.objects.filter(competition__in=competitions).all()

        if not matches.exists():
            return Response({"message": "No matches found for this campus."}, status=status.HTTP_404_NOT_FOUND)

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(matches, request, view=self)

        serializer = MatchSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

class MatchRetrieveUpdateAPIView(APIView):
    def get_permissions(self):
        if self.request.method == 'PUT':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, match_id):
        """
        Retorna uma partida específica de uma competição.
        """
        match = get_object_or_404(Match, id=match_id)

        serializer = MatchSerializer(match)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, match_id):
        """
        Atualiza uma partida específica de uma competição.
        """
        groups = request.user.groups

        match = get_object_or_404(Match, id=match_id)

        if has_role(groups, "Organizador"):
            serializer = MatchSerializer(match, data=request.data)

            if serializer.is_valid():
                match = serializer.save(partial=True)
                return Response(MatchSerializer(match).data, status=status.HTTP_200_OK)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied("Você não tem permissão para atualizar uma partida de uma competição")

class MatchStartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, match_id):
        """
        Atualiza o satus de uma partida específica de uma competição para "em andamento".
        """
        groups = request.user.groups

        match = get_object_or_404(Match, id=match_id)

        if has_role(groups, "Organizador"):
            if match.status == 'not-started':
                match.status = 'in-progress'
                match.save()
                return Response({"message": "Match status updated to in-progress."}, status=status.HTTP_200_OK)

            return Response({"message": "Match is already in progress or finished."}, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied("Você não tem permissão para atualizar o status da partida de uma competição")

class MatchFinishAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def patch(self, request,  match_id):
        """
        Atualiza o satus de uma partida específica de uma competição para "finalizada".
        """
        groups = request.user.groups

        match = get_object_or_404(Match, id=match_id)

        if has_role(groups, "Organizador"):
            if match.status == 'in-progress':
                finish_match(match)
                return Response({"message": "Match data updated and finished."}, status=status.HTTP_200_OK)

            return Response({"message": "Match is already finished or not started."}, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied("Você não tem permissão para atualizar o status da partida de uma competição")

class CompetitionStandingsAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, competition_id):
        """
        Retorna a classificação de uma competição específica.
        """

        competition = get_object_or_404(Competition, id=competition_id)
    
        standings = get_competition_standings(competition)

        if not standings.exists():
            return Response({"message": "No standings found for this competition."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ClassificationSerializer(standings, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)