from rest_framework import serializers
from competitions.models import *


class CompetitionTeamRequestSerializer(serializers.Serializer):
    team_id = serializers.UUIDField(
        help_text="UUID do time a ser inscrito na competição.")

# Serializer para a requisição de finalização de partida, pedindo os placares.


class MatchFinishRequestSerializer(serializers.Serializer):
    score_home = serializers.IntegerField(
        required=True, help_text="Placar final do time da casa.")
    score_away = serializers.IntegerField(
        required=True, help_text="Placar final do time visitante.")


class CompetitionSerializer(serializers.ModelSerializer):
    """ Descreve a estrutura completa de uma Competição. """
    modality = serializers.PrimaryKeyRelatedField(
        queryset=Modality.objects.all(), help_text="ID da modalidade associada.")
    teams_per_group = serializers.IntegerField(
        required=False, allow_null=True, help_text="Número de times por grupo na fase de grupos.")
    teams_qualified_per_group = serializers.IntegerField(
        required=False, allow_null=True, help_text="Número de times que se classificam por grupo.")

    class Meta:
        model = Competition
        fields = [
            'id', 'name', 'modality', 'status',
            'start_date', 'end_date', 'system', 'image',
            'min_members_per_team', 'max_members_per_team', 'teams_per_group', 'teams_qualified_per_group'
        ]


class ModalitySerializer(serializers.ModelSerializer):
    """ Descreve a estrutura completa de uma Modalidade. """
    id = serializers.UUIDField(format='hex_verbose', read_only=True)

    class Meta:
        model = Modality
        fields = ['id', 'name', 'campus']


class CompetitionTeamSerializer(serializers.ModelSerializer):
    """ Descreve a relação entre um Time (identificado por UUID) e uma Competição. """
    competition = CompetitionSerializer(read_only=True)

    class Meta:
        model = CompetitionTeam
        fields = ['team_id', 'competition']
        read_only_fields = ['team_id']

    def create(self, validated_data):
        if 'competition' not in validated_data:
            validated_data['competition'] = self.context.get('competition')
        return super().create(validated_data)


class CompetitionTeamsInfoSerializer(serializers.ModelSerializer):
    """ Serializer simplificado para listar os UUIDs dos times de uma competição. """
    team_uuids = serializers.SerializerMethodField()

    class Meta:
        model = Competition
        fields = ['id', 'min_members_per_team', 'team_uuids']

    def get_team_uuids(self, competition_instance):
        return competition_instance.competitionteam_set.values_list('team_id', flat=True)


class MatchSerializer(serializers.ModelSerializer):
    """ Descreve a estrutura completa de uma Partida. """
    group = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(), required=False)
    round = serializers.PrimaryKeyRelatedField(
        queryset=Round.objects.all(), required=False, allow_null=True)
    team_home = CompetitionTeamSerializer(read_only=True)
    team_away = CompetitionTeamSerializer(read_only=True)

    team_home_id = serializers.PrimaryKeyRelatedField(
        queryset=CompetitionTeam.objects.all(), source='team_home', write_only=True, required=False, allow_null=True
    )
    team_away_id = serializers.PrimaryKeyRelatedField(
        queryset=CompetitionTeam.objects.all(), source='team_away', write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = Match
        fields = ["id", "competition", "group", "round", "round_match_number", "status",
                  "scheduled_datetime", "team_home", "team_away", "team_home_id",
                  "team_away_id", "score_home", "score_away", "winner"]


class RoundSerializer(serializers.ModelSerializer):
    """ Descreve uma Rodada de uma competição. """
    class Meta:
        model = Round
        fields = ['id', 'name']


class RoundMatchesSerializer(serializers.ModelSerializer):
    """ Descreve uma Rodada e inclui a lista de partidas aninhada. """
    matches = MatchSerializer(source='match_set', many=True, read_only=True)

    class Meta:
        model = Round
        fields = ['id', 'name', 'matches']


class ClassificationSerializer(serializers.ModelSerializer):
    """ Descreve a posição de um time na tabela de classificação. """
    class Meta:
        model = Classification
        fields = [
            'id', 'team', 'position', 'points', 'games_played',
            'wins', 'draws', 'losses', 'score_pro', 'score_against',
            'score_difference',
        ]
