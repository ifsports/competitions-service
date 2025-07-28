from django.db import models
import uuid


class Modality(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, blank=False, null=False)
    campus = models.CharField(max_length=10, blank=False, null=False)

    class Meta:
        verbose_name = "Modalidade"
        verbose_name_plural = "Modalidades"

    def __str__(self):
        return self.name


class Competition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    SYSTEM_CHOICES = [
        ('league', 'League'),
        ('groups_elimination', 'Groups + Elimination'),
        ('elimination', 'Elimination Only'),
    ]

    STATUS_CHOICES = [
        ('not-started', 'Not Started'),
        ('in-progress', 'In Progress'),
        ('finished', 'Finished'),
    ]

    PHASE_CHOICES = [
        ('groups', 'Fase de Grupos'),
        ('knockout', 'Fase Eliminatória'),
        ('finished', 'Finalizada'),
    ]

    name = models.CharField(max_length=100, blank=False, null=False)
    modality = models.ForeignKey(Modality, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='not-started')
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    system = models.CharField(max_length=30, choices=SYSTEM_CHOICES)
    image = models.ImageField(upload_to='competitions/')
    min_members_per_team = models.IntegerField()
    teams_per_group = models.IntegerField(blank=True, null=True)
    teams_qualified_per_group = models.IntegerField(blank=True, null=True)
    group_elimination_phase = models.CharField(max_length=30, blank=True, null=True, choices=PHASE_CHOICES, default='groups')

    def __str__(self):
        return self.name


class Group(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    name = models.CharField(max_length=10)

    def __str__(self):
        return f'{self.competition.name} - {self.name}'


class CompetitionTeam(models.Model):
    team_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('team_id', 'competition')

    def __str__(self):
        return f'{self.team_id} @ {self.competition.name}'


class Classification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(CompetitionTeam, on_delete=models.CASCADE)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL)
    position = models.IntegerField()
    points = models.IntegerField()
    games_played = models.IntegerField()
    wins = models.IntegerField()
    losses = models.IntegerField()
    draws = models.IntegerField()
    score_pro = models.IntegerField()
    score_against = models.IntegerField()
    score_difference = models.IntegerField()

    def set_score_difference(self):
        self.score_difference = self.score_pro - self.score_against

    def save(self, *args, **kwargs):
        self.competition = self.team.competition
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Team {self.team} - {self.competition.name}'


class Round(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Match(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    STATUS_CHOICES = [
        ('not-started', 'Não iniciado'),
        ('in-progress', 'Em andamento'),
        ('finished', 'Finalizado'),
    ]

    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL)
    round = models.ForeignKey(Round, null=True, blank=True, on_delete=models.SET_NULL)
    round_match_number = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not-started')
    scheduled_datetime = models.DateTimeField(null=True, blank=True)
    team_home = models.ForeignKey(CompetitionTeam, related_name='home_team', on_delete=models.CASCADE, null=True, blank=True)
    team_away = models.ForeignKey(CompetitionTeam, related_name='away_team', on_delete=models.CASCADE, null=True, blank=True)

    home_feeder_match = models.ForeignKey('self', related_name='feeds_home_team', on_delete=models.SET_NULL, null=True, blank=True)
    away_feeder_match = models.ForeignKey('self', related_name='feeds_away_team', on_delete=models.SET_NULL, null=True, blank=True)


    score_home = models.IntegerField(null=True, blank=True)
    score_away = models.IntegerField(null=True, blank=True)
    winner = models.ForeignKey(CompetitionTeam, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f'{self.team_home} vs {self.team_away}'