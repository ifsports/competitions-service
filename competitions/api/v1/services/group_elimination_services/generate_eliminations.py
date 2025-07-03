from math import log2, ceil
from django.db.models import Q

# Importe os seus modelos
from competitions.models import Competition, Group, Round, Match, Classification

def generate_elimination_stage(competition: Competition):
    """
    Gera a estrutura completa da fase eliminatória, incluindo as ligações
    (feeder) entre as partidas.
    """
    if not competition.teams_qualified_per_group:
        print("AVISO: Geração da fase eliminatória pulada.")
        return

    num_groups = Group.objects.filter(competition=competition).count()
    total_qualified_teams = num_groups * competition.teams_qualified_per_group

    if total_qualified_teams < 2 or not is_power_of_two(total_qualified_teams):
         print(f"AVISO: Fase eliminatória não pode ser gerada. O número de classificados ({total_qualified_teams}) não é uma potência de 2.")
         return

    round_names = get_elimination_round_names(total_qualified_teams)
    
    # 1. GERAÇÃO DA PRIMEIRA RODADA (SEM FEEDERS)
    round_obj = Round.objects.create(name=round_names[0])
    num_matches_first_round = total_qualified_teams // 2
    
    previous_round_matches = []
    for i in range(1, num_matches_first_round + 1):
        match = Match.objects.create(
            competition=competition, round=round_obj,
            team_home=None, team_away=None,
            round_match_number=i, status='pending',
        )
        previous_round_matches.append(match)
        
    # 2. GERAÇÃO DAS RODADAS SUBSEQUENTES COM LIGAÇÕES FEEDER
    for round_index in range(1, len(round_names)):
        round_name = round_names[round_index]
        round_obj = Round.objects.create(name=round_name)
        current_round_matches = []
        
        match_pairs = zip(previous_round_matches[::2], previous_round_matches[1::2])

        for i, (home_feeder, away_feeder) in enumerate(match_pairs, start=1):
            match = Match.objects.create(
                competition=competition, round=round_obj,
                team_home=None, team_away=None,
                round_match_number=i, status='pending',
                home_feeder_match=home_feeder,
                away_feeder_match=away_feeder,
            )
            current_round_matches.append(match)
            
        previous_round_matches = current_round_matches
    
    print(f"Estrutura da fase eliminatória gerada para a competição {competition.name}.")


# --- FUNÇÃO DE ATRIBUIÇÃO (CHAMAR APÓS O FIM DA FASE DE GRUPOS) ---
def assign_teams_to_knockout_stage(competition: Competition):
    """
    Preenche as partidas da primeira rodada eliminatória com as equipes reais.
    """
    print(f"Iniciando a atribuição de equipes para a fase eliminatória: {competition.name}")
    
    clashes = create_first_round_clashes(competition)
    if not clashes: return

    round_names = get_elimination_round_names(len(clashes))
    first_round_matches = Match.objects.filter(
        competition=competition,
        round__name=round_names[0]
    ).order_by('round_match_number')

    if len(first_round_matches) != len(clashes):
        print("ERRO: O número de partidas não corresponde ao de confrontos.")
        return

    placeholder_to_real_team_map = {}
    groups = Group.objects.filter(competition=competition)
    for group in groups:
        standings = Classification.objects.filter(group=group).order_by('position')
        for classification in standings:
            placeholder_name = f"{classification.position}º {group.name}"
            placeholder_to_real_team_map[placeholder_name] = classification.team
    
    matches_to_update = []
    for i, match in enumerate(first_round_matches):
        home_placeholder_name, away_placeholder_name = clashes[i]
        
        match.team_home = placeholder_to_real_team_map.get(home_placeholder_name)
        match.team_away = placeholder_to_real_team_map.get(away_placeholder_name)
        
        if not match.team_home or not match.team_away:
            print(f"AVISO: Não foi possível encontrar a equipe para o confronto {home_placeholder_name} vs {away_placeholder_name}")
            continue
        matches_to_update.append(match)

    Match.objects.bulk_update(matches_to_update, ['team_home', 'team_away'])
    print(f"Atribuição concluída. {len(matches_to_update)} partidas foram atualizadas.")


# --- FUNÇÃO DE ATUALIZAÇÃO (CHAMAR QUANDO UMA PARTIDA TERMINA) ---
def update_next_match_after_finish(finished_match: Match):
    """
    Esta função é chamada quando uma partida termina. Ela encontra a próxima
    partida no chaveamento e atualiza com a equipe vencedora.
    """
    if not finished_match.winner:
        return

    # Busca por partidas que são alimentadas pela que acabou de terminar
    # Esta query é extremamente rápida e eficiente!
    next_matches = Match.objects.filter(
        Q(home_feeder_match=finished_match) | Q(away_feeder_match=finished_match)
    )

    matches_to_save = []
    for next_match in next_matches:
        if next_match.home_feeder_match == finished_match:
            next_match.team_home = finished_match.winner
        if next_match.away_feeder_match == finished_match:
            next_match.team_away = finished_match.winner
        
        matches_to_save.append(next_match)

    # Atualiza todas as partidas encontradas de uma vez
    Match.objects.bulk_update(matches_to_save, ['team_home', 'team_away'])
    print(f"{len(matches_to_save)} partidas foram atualizadas com o vencedor da partida {finished_match.id}")


def create_first_round_clashes(competition: Competition) -> list[tuple[str, str]]:
    """Cria os confrontos da primeira rodada com um sistema de seeding correto."""
    groups = list(Group.objects.filter(competition=competition).order_by('name'))
    num_qualified_per_group = competition.teams_qualified_per_group
    all_placeholders = []
    for i in range(1, num_qualified_per_group + 1):
        for group in groups:
            all_placeholders.append(f"{i}º {group.name}")
    num_clashes = len(all_placeholders) // 2
    high_seeds = all_placeholders[:num_clashes]
    low_seeds = all_placeholders[num_clashes:]
    low_seeds.reverse()
    return list(zip(high_seeds, low_seeds))

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
