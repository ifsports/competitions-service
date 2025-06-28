import asyncio
from itertools import combinations
import random
from competitions.models import Competition, Round, CompetitionTeam, Match, Classification, Group
from competitions.api.v1.messaging.publishers import publish_match_created

from math import ceil

def generate_groups_elimination_competition(competition: Competition):
    """
    Gera uma competição completa no formato 'Fase de Grupos + Eliminatórias'.
    """
    teams = list(CompetitionTeam.objects.filter(competition=competition))
    random.shuffle(teams)

    if not teams or not competition.teams_per_group or competition.teams_per_group <= 1:
        raise ValueError("A competição precisa de times e a configuração 'times por grupo' deve ser maior que 1.")

    # 1. Cria os grupos e as entradas na tabela de classificação
    groups = create_groups_and_classification(competition, teams)

    # 2. Gera as partidas da fase de grupos
    for group in groups:
        generate_group_matches(competition, group)

    # 3. Gera as partidas da fase eliminatória
    generate_elimination_stage(competition)


def create_groups_and_classification(competition: Competition, teams: list):
    """Cria os grupos, distribui os times e inicializa a classificação para cada time."""
    num_teams = len(teams)
    teams_per_group = competition.teams_per_group
    num_groups = ceil(num_teams / teams_per_group)
    groups = []
    team_iterator = iter(teams)

    for i in range(num_groups):
        group_name = f'Grupo {chr(65 + i)}'
        group = Group.objects.create(competition=competition, name=group_name)
        groups.append(group)

        for _ in range(teams_per_group):
            try:
                team = next(team_iterator)
                Classification.objects.create(
                    team=team, competition=competition, group=group, position=0,
                    points=0, games_played=0, wins=0, losses=0, draws=0,
                    score_pro=0, score_against=0, score_difference=0,
                )
            except StopIteration:
                break
    return groups


def generate_group_matches(competition: Competition, group: Group):
    """Gera as partidas para um único grupo."""
    teams_in_group = CompetitionTeam.objects.filter(competition=competition, classification__group=group)

    if teams_in_group.count() < 2:
        return

    all_matches_combinations = list(combinations(teams_in_group, 2))
    round_obj, _ = Round.objects.get_or_create(name=f'Fase de Grupos - {group.name}')

    for i, (team1, team2) in enumerate(all_matches_combinations, start=1):
        home_team, away_team = (team1, team2) if random.random() > 0.5 else (team2, team1)
        match = Match.objects.create(
            competition=competition, group=group, round=round_obj,
            team_home=home_team, team_away=away_team,
            round_match_number=i, status='pending',
        )

        match_data = {
            'match_id': str(match.id),
            'team_home_id': str(match.team_home.team_id),
            'team_away_id': str(match.team_away.team_id),
            'status': 'pending',
        }

        # Publica a partida criada no RabbitMQ
        try:
            asyncio.get_event_loop().run_until_complete(publish_match_created(match_data))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(publish_match_created(match_data))

def generate_elimination_stage(competition: Competition):
    pass