from competitions.models import Group, Classification, Competition

def get_group_competition_standings(competition: Competition):
    """
    Retorna a classificação de uima competição de fase de grupos'.
    """
    return Classification.objects.filter(
            competition=competition,
        ).order_by('group__name', 'position')

def update_group_standings(group: Group):
    """
    Atualiza as posições dos times de um grupo
    """
    classifications = list(
        Classification.objects.filter(group=group).order_by(
            '-points',  
            '-score_difference',
            '-score_pro',
        )
    )

    for i, classification in enumerate(classifications, start=1):
        classification.position = i

    Classification.objects.bulk_update(classifications, ['position'])