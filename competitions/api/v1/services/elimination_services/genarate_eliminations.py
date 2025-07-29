import asyncio
from math import log2, ceil
import random

from ...messaging.publishers import publish_match_created

from competitions.models import Competition, CompetitionTeam, Round, Match

def generate_elimination_only_competition(competition: Competition):
    """
    Gera a árvore de confrontos para uma competição de eliminatória simples.

    ESTRATÉGIA:
    1. Busca todas as equipes inscritas na competição.
    2. Realiza o seeding (neste caso, aleatório).
    3. Lida com um número de equipes que não é uma potência de 2, criando uma
       rodada preliminar para os piores "seeds" e dando "bye" para os melhores.
    4. Gera todas as rodadas e partidas, já com as ligações "feeder" quando aplicável.
    """

    print(f"Iniciando a geração da competição eliminatória: {competition.name}")
    
    # 1. Busca e Semeia (Seed) as Equipes
    all_teams = list(CompetitionTeam.objects.filter(competition=competition))
    
    # Seeding Aleatório: Embaralha a lista de equipes.
    # Se você tivesse um ranking, ordenaria a lista aqui em vez de embaralhar.
    random.shuffle(all_teams)
    
    num_teams = len(all_teams)
    if num_teams < 2:
        print("ERRO: São necessárias pelo menos 2 equipes para uma competição eliminatória.")
        return

    # 2. Lida com um número de equipes que não é uma potência de 2
    next_power_of_two = 2**ceil(log2(num_teams))
    num_byes = next_power_of_two - num_teams
    num_preliminary_matches = num_teams - num_byes
    
    # As equipes com "bye" são as melhores semeadas (as primeiras da lista embaralhada)
    teams_with_bye = all_teams[:num_byes]
    # As equipes que jogam a fase preliminar são as piores semeadas
    teams_in_preliminary = all_teams[num_byes:]

    print(f"Total de equipes: {num_teams}")
    print(f"Equipes com 'bye' (avançam direto): {num_byes}")
    print(f"Equipes na rodada preliminar: {len(teams_in_preliminary)}")

    # 3. Gera a Rodada Preliminar (se necessário)
    preliminary_round_matches = []
    if num_preliminary_matches > 0:
        preliminary_round = Round.objects.create(name="Rodada Preliminar")
        
        # Agrupa as equipes da preliminar de 2 em 2
        match_pairs = zip(teams_in_preliminary[::2], teams_in_preliminary[1::2])
        
        for i, (team1, team2) in enumerate(match_pairs, start=1):
            match = Match.objects.create(
                competition=competition,
                round=preliminary_round,
                team_home=team1,
                team_away=team2,
                round_match_number=i,
                status='pending'
            )

            match_data = {
                'match_id': str(match.id),
                'team_home_id': str(match.team_home.team_id),
                'team_away_id': str(match.team_away.team_id),
                'status': 'pending',
                'competition_id': str(competition.id),
            }

            # Publica a partida criada no RabbitMQ
            try:
                asyncio.get_event_loop().run_until_complete(publish_match_created(match_data))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(publish_match_created(match_data))


            preliminary_round_matches.append(match)

    # 4. Gera a Árvore Principal
    # As equipes na próxima rodada são uma mistura das que tiveram "bye" e
    # dos vencedores da rodada preliminar.
    
    # Os "feeders" da próxima rodada
    next_round_feeders = [
        *teams_with_bye,          # Equipes reais que passaram direto
        *preliminary_round_matches # Partidas que "alimentarão" as próximas vagas
    ]
    
    # Embaralha os feeders para que uma equipe com bye possa enfrentar outra
    random.shuffle(next_round_feeders)
    
    previous_round_feeders = next_round_feeders
    round_names = get_elimination_round_names(next_power_of_two)

    for round_index, round_name in enumerate(round_names):
        round_obj = Round.objects.create(name=round_name)
        current_round_feeders = []
        
        # Agrupa os "feeders" da rodada anterior de 2 em 2
        feeder_pairs = zip(previous_round_feeders[::2], previous_round_feeders[1::2])

        for i, (home_feeder, away_feeder) in enumerate(feeder_pairs, start=1):
            
            # Lógica para atribuir os times ou os feeders
            team_home, team_away = None, None
            feeder_home, feeder_away = None, None

            if isinstance(home_feeder, CompetitionTeam):
                team_home = home_feeder
            else: # É uma partida (Match)
                feeder_home = home_feeder

            if isinstance(away_feeder, CompetitionTeam):
                team_away = away_feeder
            else: # É uma partida (Match)
                feeder_away = away_feeder

            match = Match.objects.create(
                competition=competition,
                round=round_obj,
                team_home=team_home,
                team_away=team_away,
                home_feeder_match=feeder_home,
                away_feeder_match=feeder_away,
                round_match_number=i,
                status='pending',
            )

            match_data = {
                'match_id': str(match.id),
                'team_home_id': str(match.team_home.team_id),
                'team_away_id': str(match.team_away.team_id),
                'status': 'pending',
                'competition_id': str(competition.id),
            }

            # Publica a partida criada no RabbitMQ
            try:
                asyncio.get_event_loop().run_until_complete(publish_match_created(match_data))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(publish_match_created(match_data))

            current_round_feeders.append(match)
        
        previous_round_feeders = current_round_feeders
        
    print(f"Competição eliminatória '{competition.name}' gerada com sucesso.")

def get_elimination_round_names(num_teams: int) -> list:
    """Retorna uma lista com os nomes das fases eliminatórias."""
    if num_teams < 2:
        return []
        
    num_rounds = int(log2(num_teams))
    names = []
    
    round_name_map = {
        1: "Final", 
        2: "Semifinais", 
        4: "Quartas de Final", 
        8: "Oitavas de Final", 
        16: "16-avos de Final"
    }

    for i in range(num_rounds):
        num_matches_in_stage = 2**(num_rounds - 1 - i)
        
        round_name = round_name_map.get(num_matches_in_stage, f'Fase de {num_matches_in_stage * 2}')
        names.append(round_name)
        
    return names

def is_power_of_two(n: int) -> bool:
    """Verifica se um número é uma potência de 2."""
    return (n > 0) and (n & (n - 1) == 0)
