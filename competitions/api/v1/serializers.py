from rest_framework import serializers
from competitions.models import *

class CompetitionSerializer(serializers.ModelSerializer):
    modality = serializers.PrimaryKeyRelatedField(queryset=Modality.objects.all())
    image = serializers.ImageField(required=False, allow_null=True)
    min_members_per_team = serializers.IntegerField(required=False, allow_null=True)
    teams_per_group = serializers.IntegerField(required=False, allow_null=True)
    teams_qualified_per_group = serializers.IntegerField(required=False, allow_null=True)
    
    class Meta:
        model = Competition
        fields = [
            'id', 'name', 'modality', 'status',
            'start_date', 'end_date', 'system', 'image',
            'min_members_per_team', 'teams_per_group', 'teams_qualified_per_group'
        ]

class ModalitySerializer(serializers.ModelSerializer):
    campus = serializers.PrimaryKeyRelatedField(queryset=Campus.objects.all(), required=False)
    id = serializers.IntegerField(required=False, read_only=True)

    class Meta:
        model = Modality
        fields = ['id', 'name', 'campus']

    def create(self, validated_data):
        # Pega o campus do contexto se não foi enviado nos dados
        if 'campus' not in validated_data and 'campus_code' not in self.context:
            raise serializers.ValidationError("Campus is required to create a modality.")
        if 'campus' not in validated_data:
            validated_data['campus'] = self.context.get('campus')
        return super().create(validated_data)

class CompetitionTeamSerializer(serializers.ModelSerializer):
    competition = serializers.PrimaryKeyRelatedField(queryset=Competition.objects.all())
    
    class Meta:
        model = CompetitionTeam
        fields = ['team_id', 'competition']
        read_only_fields = ['team_id']

    def create(self, validated_data):
        if 'competition' not in validated_data:
            validated_data['competition'] = self.context.get('competition')
        return super().create(validated_data)

class MatchSerializer(serializers.ModelSerializer):
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), required=False)
    round = serializers.PrimaryKeyRelatedField(queryset=Round.objects.all(), required=False)
    team_home = CompetitionTeamSerializer(read_only=True)
    team_away = CompetitionTeamSerializer(read_only=True)

    
    class Meta:
        model = Match
        fields = ["id","competition", "group", "round", "round_match_number" "status", "scheduled_datetime", "team_home",
                    "team_away", "score_home", "score_away", "winner",]

class RoundSerializer(serializers.ModelSerializer):
    """
        Returns rounds for a given competition.
    """

    class Meta:
        model = Round
        fields = ['id', 'name']

class RoundMatchesSerializer(serializers.ModelSerializer):
    """'
        Returns rounds and matches for a given round.
    """
    matches = MatchSerializer(source='match_set', many=True, read_only=True)

    class Meta:
        model = Round
        fields = ['id', 'name', 'matches']

class ClassificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Classification
        fields = [
            'id',
            'team',
            'position',
            'points',
            'games_played',
            'wins',
            'draws',
            'losses',
            'score_pro',
            'score_against',
            'score_difference',
        ]