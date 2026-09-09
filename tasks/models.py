from django.conf import settings
from django.db import models
from django.utils import timezone

from core.fields import EncryptedTextField


class TaskQuerySet(models.QuerySet):
    def pending_reminders(self, as_of=None):
        """Tarefas com lembrete pendente de disparo em `as_of` (agora, por
        padrão): lembrete habilitado, ainda não enviado, tarefa não
        concluída e horário de lembrete já alcançado.

        Restringe a busca no banco a uma janela ampla (`scheduled_for` até
        `as_of`, já que a maior antecedência configurável é de 2 dias) e
        filtra o cálculo exato de `remind_at` em Python — evita depender de
        aritmética de datas específica de cada banco (Postgres/SQLite).
        """
        as_of = as_of or timezone.now()
        candidates = self.filter(
            remind_enabled=True,
            remind_minutes_before__isnull=False,
            reminder_sent_at__isnull=True,
        ).exclude(status=Task.Status.DONE).filter(
            scheduled_for__lte=as_of + timezone.timedelta(days=2)
        )
        return [task for task in candidates if task.remind_at and task.remind_at <= as_of]


class Task(models.Model):
    """Uma tarefa agendável do usuário, exibida no painel e no calendário,
    com lembrete opcional configurável (quanto tempo antes avisar).
    """

    class Status(models.TextChoices):
        TODO = "todo", "A fazer"
        IN_PROGRESS = "in_progress", "Em andamento"
        DONE = "done", "Concluída"

    class ReminderOffset(models.IntegerChoices):
        MIN_10 = 10, "10 minutos antes"
        MIN_30 = 30, "30 minutos antes"
        HOUR_1 = 60, "1 hora antes"
        HOUR_3 = 180, "3 horas antes"
        DAY_1 = 1440, "1 dia antes"
        DAY_2 = 2880, "2 dias antes"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks"
    )
    title = models.CharField("título", max_length=200)
    notes = EncryptedTextField("notas", blank=True, default="")
    status = models.CharField("status", max_length=15, choices=Status.choices, default=Status.TODO)
    scheduled_for = models.DateTimeField("agendada para")

    remind_enabled = models.BooleanField("quero ser lembrado", default=False)
    remind_minutes_before = models.PositiveIntegerField(
        "avisar com quanto tempo de antecedência",
        choices=ReminderOffset.choices,
        null=True,
        blank=True,
        help_text="Só é usado se \"quero ser lembrado\" estiver marcado.",
    )

    completed_at = models.DateTimeField("concluída em", null=True, blank=True)
    reminder_sent_at = models.DateTimeField(
        "lembrete enviado em", null=True, blank=True,
        help_text="Preenchido pelo worker de lembretes quando o aviso é disparado.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_for"]
        indexes = [
            models.Index(fields=["owner", "scheduled_for"]),
            models.Index(fields=["owner", "status"]),
        ]

    objects = TaskQuerySet.as_manager()

    def __str__(self):
        return self.title

    @property
    def is_overdue(self) -> bool:
        return self.status != self.Status.DONE and self.scheduled_for < timezone.now()

    @property
    def remind_at(self):
        """Horário em que o lembrete deveria disparar, ou None se a tarefa
        não tem lembrete configurado.
        """
        if not self.remind_enabled or not self.remind_minutes_before:
            return None
        return self.scheduled_for - timezone.timedelta(minutes=self.remind_minutes_before)

    def mark_complete(self) -> None:
        self.status = self.Status.DONE
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

    def mark_reminder_sent(self) -> None:
        self.reminder_sent_at = timezone.now()
        self.save(update_fields=["reminder_sent_at", "updated_at"])
