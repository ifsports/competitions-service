from competitions.models import Group, Classification

def get_group_standings(group: Group):
    """
    Retorna a classificação dos times em uma competição do tipo 'league'.
    """
    classifications = Classification.objects.filter(group=group).order_by(
            '-points',  
            '-score_difference',
    )

    return classifications

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