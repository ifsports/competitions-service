from competitions.models import Competition, Round, CompetitionTeam, Match, Classification
from competitions.api.v1.messaging.publishers import publish_match_created
import asyncio

def generate_league_competition(competition: Competition):
    """
    Gera uma competição do tipo 'league' com rounds (rodadas) e jogos.
    """
    teams = list(CompetitionTeam.objects.filter(competition=competition))
    total_teams = len(teams)

    if total_teams < 2:
        raise ValueError("A competição deve ter pelo menos 2 times.")

    # Adiciona 'placeholder_team' se o total de equipes for ímpar
    placeholder_team = None
    if total_teams % 2 != 0:
        placeholder_team = CompetitionTeam(team_id=None)
        teams.append(placeholder_team)
        total_teams += 1

    num_rounds = total_teams - 1
    matches_per_round = total_teams // 2

    rounds = []

    for round_number in range(1, num_rounds + 1):
        round_matches = []
        for i in range(matches_per_round):
            home = teams[i]
            away = teams[total_teams - 1 - i]
            # Ignora partidas com o placeholder_team
            if home != placeholder_team and away != placeholder_team:
                round_matches.append((home, away))
        rounds.append(round_matches)

        # Rotaciona os times (exceto o primeiro)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]

    # Criar matches organizados por rodada
    for idx, round_matches in enumerate(rounds, start=1):
        round_obj = Round.objects.create(name=f'Rodada {idx}')
        for match_number, (home, away) in enumerate(round_matches, start=1):
            Match.objects.create(
                competition=competition,
                round=round_obj,
                team_home=home,
                team_away=away,
                round_match_number=match_number,
                status='pending',
            )

            match_data = {
                'competition_id': competition.id,
                'round_id': round_obj.id,
                'team_home_id': home.team_id,
                'team_away_id': away.team_id,
                'round_match_number': match_number,
                'status': 'pending',
            }

            # Publica a partida criada no RabbitMQ
            try:
                asyncio.get_event_loop().run_until_complete(publish_match_created(match_data))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(publish_match_created(match_data))

def generate_knockout_competition(competition: Competition):
    pass

def generate_groups_elimination(competition: Competition):
    pass

def get_league_standings(competition: Competition):
    """
    Retorna a classificação dos times em uma competição do tipo 'league'.
    """
    classifications = Classification.objects.filter(competition=competition).order_by(
            '-points',  
            '-score_difference',
    )

    return classifications

def update_league_standings(competition: Competition):
    """
    Atualiza as posições dos times em uma competição de liga com base na pontuação e saldo.
    """
    classifications = list(
        Classification.objects.filter(competition=competition).annotate(
        ).order_by(
            '-points',  
            '-score_difference',
        )
    )

    for i, classification in enumerate(classifications, start=1):
        classification.position = i

    Classification.objects.bulk_update(classifications, ['position'])

def update_teams_statistics(match: Match):
    """
    Atualiza as estatísticas dos times.
    """
    # Pega os times envolvidos na partida
    team_home = match.team_home
    team_away = match.team_away
    
    # Pega o placar da partida
    score_home = match.score_home
    score_away = match.score_away

    # Atualiza os gols marcados e sofridos dos times
    team_away.score_pro += score_away
    team_away.score_against += score_home

    # Atualiza os gols marcados e sofridos dos times
    team_home.score_pro += score_home
    team_home.score_against += score_away
    
    # Atualiza o saldo de gols dos times
    team_away.set_score_difference()
    team_home.set_score_difference()

    if score_home > score_away:
        # Team home vence
        team_home.wins += 1
        team_away.losses += 1
        
        team_home.points += 3
        team_away.points += 0

        match.winner = team_home
    elif score_home < score_away:
        # Team away vence
        team_away.wins += 1
        team_home.losses += 1

        team_away.points += 3
        team_home.points += 0

        match.winner = team_away
    else:
        # Empate
        team_home.draws += 1
        team_away.draws += 1

        team_home.points += 1
        team_away.points += 1

        match.winner = None

    # Atualiza a quantidade de jogos jogados de cada time
    team_home.games_played += 1
    team_away.games_played += 1

    # Salva as alterações na partida
    match.status = 'finished'
    match.save()

    # Salva as alterações nos times
    team_home.save()
    team_away.save()

def finish_match(match: Match):
    """
    Atualiza as estatísticas dos times e a classificação após o término de uma partida.
    """

    update_teams_statistics(match)

    # Atualiza a classificação dos times com base no tipo da competição
    if match.competition.system == 'league':
        update_league_standings(competition=match.competition)
    elif match.competition.system == 'elimination':
        # Será implementado posteriormente
        pass
    elif match.competition.system == 'groups_elimination':
        # Será implementado posteriormente
        pass

def get_competition_standings(competition: Competition):
    """
    Retorna a classificação dos times em uma competição.
    """
    if competition.system == 'league':
        return get_league_standings(competition)
    elif competition.system == 'elimination':
        # Será implementado posteriormente
        pass
    elif competition.system == 'groups_elimination':
        # Será implementado posteriormente
        pass
    else:
        raise ValueError("Tipo de competição desconhecido.")