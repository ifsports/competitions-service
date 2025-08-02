from competitions.models import Competition, Round, CompetitionTeam, Match, Classification, Group
from competitions.api.v1.messaging.publishers import publish_match_created
from competitions.api.v1.services.group_elimination_services.groups_strandings import update_group_standings, get_group_competition_standings
from competitions.api.v1.services.group_elimination_services.generate_eliminations import update_next_match_after_finish
import asyncio

from django.db.models import Case, When, Value, IntegerField

import uuid
from django.db import transaction, IntegrityError, close_old_connections


def generate_league_competition(competition: Competition):
    """
    Gera uma competição do tipo 'league' com rounds (rodadas) e jogos.
    """
    teams = list(CompetitionTeam.objects.filter(competition=competition))
    
# --- NOVO TRECHO: Início da criação da classificação ---
    # Prepara a criação da classificação para cada time
    classifications_to_create = [
        Classification(
            competition=competition,
            team=team,
            points=0,
            position=0,
            games_played=0,
            wins=0,
            draws=0,
            losses=0,
	    score_pro=0,
            score_against=0,
	    score_difference=0
        ) for team in teams
    ]
    # Cria todos os objetos de classificação em uma única consulta
    if classifications_to_create:
        Classification.objects.bulk_create(classifications_to_create)
    # --- FIM DO NOVO TRECHO ---

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
            match = Match.objects.create(
                competition=competition,
                round=round_obj,
                team_home=home,
                team_away=away,
                round_match_number=match_number,
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

def get_league_standings(competition: Competition):
    """
    Retorna a classificação dos times em uma competição do tipo 'league'.
    """
    classifications = Classification.objects.filter(competition=competition).order_by('position')

    return classifications

def get_ordered_elimination_matches(competition: Competition): # Nome da função melhorado
    """
    Retorna as partidas de uma fase eliminatória, ordenadas pelas fases
    (16-avos, Oitavas, Quartas, etc.) e pelo número da partida.
    """
    
    ordem_fases = [
        '16-avos de Final',
        'Oitavas de Final',
        'Quartas de Final',
        'Semifinal',
        'Final'
    ]

    ordem_personalizada = Case(
        *[When(round__name=fase, then=Value(i)) for i, fase in enumerate(ordem_fases)],
        default=Value(len(ordem_fases)), 
        output_field=IntegerField()
    )

    matches = Match.objects.filter(
        competition=competition 
    ).select_related(
        'round', 'team_home', 'team_away', 'winner' 
    ).annotate(
        ordem_da_fase=ordem_personalizada 
    ).order_by(
        'ordem_da_fase', 'round_match_number'
    )

    return matches

def update_league_standings(competition: Competition):
    """
    Atualiza as posições dos times em uma competição de liga com base na pontuação e saldo.
    """
    classifications = list(
        Classification.objects.filter(competition=competition).annotate(
        ).order_by(
            '-points',  
            '-score_difference',
            '-score_pro',
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

    # Salva as alterações nas classificações dos times
    team_home.save()
    team_away.save()

def finish_match(match: Match):
    """
    Atualiza as estatísticas dos times e a classificação após o término de uma partida.
    """

    update_teams_statistics(match)

    if match.competition.system == 'league':
        update_league_standings(competition=match.competition)
        
    elif match.competition.system == 'elimination':
        update_next_match_after_finish(match)

    elif match.competition.system == 'groups_elimination':
        if match.competition.group_elimination_phase == 'groups':
            group = match.group
            if group:
                update_group_standings(group)
            else:
                raise ValueError("A partida não está associada a um grupo válido.")
        elif match.competition.group_elimination_phase == 'knockout':
            update_next_match_after_finish(match)
        else:
            raise ValueError("Fase desconhecida ou competição finalizada.")
        
def get_competition_standings(competition: Competition):
    """
    Retorna a classificação dos times em uma competição.
    """
    if competition.system == 'league':
        return get_league_standings(competition)
    elif competition.system == 'elimination':
        return get_ordered_elimination_matches(competition)
    elif competition.system == 'groups_elimination':
        if competition.group_elimination_phase == 'groups':
            return get_group_competition_standings(competition)
        elif competition.group_elimination_phase == 'knockout':
            return get_ordered_elimination_matches(competition)
    else:
        raise ValueError("Tipo de competição desconhecido.")

def update_team_from_request_in_db_django(message_data: dict) -> dict:
    """
    Processa a mensagem e atualiza/cria entidades no banco de dados usando Django ORM.
    """
    close_old_connections()

    try:
        print(f"DJANGO_DB: Processando mensagem: {message_data}")

        team_id_str = message_data.get("team_id")
        request_type_str = message_data.get("request_type")
        status_str = message_data.get("status")
        competition_id_str = message_data.get("competition_id")

        if not team_id_str:
            raise ValueError("'team_id' é obrigatório na mensagem")
        if not request_type_str:
            raise ValueError("'request_type' é obrigatório na mensagem")
        if not status_str:
            raise ValueError("'status' da solicitação é obrigatório na mensagem")
        if not competition_id_str:
            raise ValueError("'competition_id' da solicitação é obrigatório na mensagem")

        try:
            team_id_for_db = uuid.UUID(team_id_str)
        except ValueError:
            raise ValueError(f"team_id '{team_id_str}' não é um UUID válido")

        try:
            competition_id_for_db = uuid.UUID(competition_id_str)
        except ValueError:
            raise ValueError(f"competition_id '{competition_id_str}' não é um UUID válido")

        print(
            f"DJANGO_DB: Dados parseados: team_id={team_id_for_db}, request_type={request_type_str}, request_status={status_str}")

        with transaction.atomic():
            try:
                competition_instance = Competition.objects.filter(id=competition_id_for_db).first()
            except Competition.DoesNotExist:
                raise ValueError(f"Competition com ID '{competition_id_for_db}' não encontrada.")

            if request_type_str == "approve_team":
                try:
                    competition_team_instance, created = CompetitionTeam.objects.get_or_create(
                        team_id=team_id_for_db,
                        competition=competition_instance,
                    )

                    if created:
                        message = f"Equipe {team_id_for_db} associada à competição {competition_id_for_db} com sucesso."
                        print(f"DJANGO_DB: {message}")
                        return {"status": "success", "message": message,
                                "competition_team_id": str(competition_team_instance.team_id)}
                    else:
                        message = f"Equipe {team_id_for_db} já estava associada à competição {competition_id_for_db}."
                        print(f"DJANGO_DB: {message}")
                        return {"status": "already_exists", "message": message,
                                "competition_team_id": str(competition_team_instance.team_id)}

                except IntegrityError as ie:
                    print(f"DJANGO_DB: Erro de integridade ao criar CompetitionTeam: {ie}")
                    existing_entry = CompetitionTeam.objects.filter(team_id=team_id_for_db,
                                                                    competition=competition_instance).first()
                    if existing_entry:
                        return {"status": "already_exists",
                                "message": f"Equipe {team_id_for_db} já associada (detectado por IntegrityError).",
                                "competition_team_id": str(existing_entry.team_id)}
                    raise

            elif request_type_str == "delete_team":
                try:
                    competition_team_instance = CompetitionTeam.objects.filter(
                        team_id=team_id_for_db,
                        competition=competition_instance,
                    ).first()

                    if competition_team_instance:
                        competition_team_instance.delete()
                        message = f"Equipe {team_id_for_db} removida da competição {competition_id_for_db} com sucesso."
                        print(f"DJANGO_DB: {message}")
                        return {"status": "success", "message": message}
                    else:
                        message = f"Equipe {team_id_for_db} não estava associada à competição {competition_id_for_db}."
                        print(f"DJANGO_DB: {message}")
                        return {"status": "not_found", "message": message}

                except Exception as e:
                    print(f"DJANGO_DB: Erro ao deletar CompetitionTeam: {e}")
                    return {"status": "error", "message": f"Erro ao remover equipe: {str(e)}"}


    except ValueError as ve:
        print(f"DJANGO_DB: Erro de dados ou validação: {ve}")
        raise
    except Exception as e:
        print(f"DJANGO_DB: Erro inesperado no banco: {e}")
        raise
    finally:
        close_old_connections()

def handle_match_finished_message(message_data: dict) -> dict:
    """
    Processa a mensagem e atualiza/cria entidades no banco de dados usando Django ORM.
    """
    close_old_connections()

    try:
        print(f"DJANGO_DB: Processando mensagem: {message_data}")

        match_id_str = message_data.get("match_id")
        team_home_str = message_data.get("team_home_id")
        team_away_str = message_data.get("team_away_id")
        score_home = message_data.get("score_home")
        score_away = message_data.get("score_away")
        status_str = message_data.get("status")

        if not match_id_str:
            raise ValueError("'match_id' é obrigatório na mensagem")
        if score_home is None:
            raise ValueError("'score_home' da solicitação é obrigatório na mensagem")
        if score_away is None:
            raise ValueError("'score_away' da solicitação é obrigatório na mensagem")

        try:
            match_id_for_db = uuid.UUID(match_id_str)
        except ValueError:
            raise ValueError(f"match_id '{match_id_str}' não é um UUID válido")

        try:
            team_home_for_db = uuid.UUID(team_home_str)
        except ValueError:
            raise ValueError(f"team_id '{team_home_str}' não é um UUID válido")

        try:
            team_away_for_db = uuid.UUID(team_away_str)
        except ValueError:
            raise ValueError(f"team_id '{team_away_str}' não é um UUID válido")

        with transaction.atomic():
            if status_str == "finished":

                updated = Match.objects.filter(id=match_id_for_db).update(
                    score_home=score_home,
                    score_away=score_away,
                )

                match = Match.objects.filter(id=match_id_for_db).first()

                if updated == 0:
                    raise ValueError(f"Match com ID '{match_id_for_db}' não encontrada.")
                
                finish_match(match)

    except ValueError as ve:
        print(f"DJANGO_DB: Erro de dados ou validação: {ve}")
        raise
    except Exception as e:
        print(f"DJANGO_DB: Erro inesperado no banco: {e}")
        raise
    finally:
        close_old_connections()
