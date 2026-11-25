import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tasks.models import Task


class Command(BaseCommand):
    help = "Verifica tarefas com lembrete pendente e as marca como notificadas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop", action="store_true",
            help="Roda continuamente, verificando a cada --interval segundos.",
        )
        parser.add_argument(
            "--interval", type=int, default=30,
            help="Segundos entre verificações quando --loop é usado (padrão: 30).",
        )
        parser.add_argument(
            "--max-iterations", type=int, default=None,
            help="Limita o número de passadas quando --loop é usado. "
                 "Pensado para testes automatizados; omitido, roda para sempre.",
        )

    def handle(self, *args, **options):
        if options["loop"]:
            self._run_loop(options["interval"], options["max_iterations"])
        else:
            self._run_once()

    def _run_loop(self, interval: int, max_iterations):
        iterations = 0
        try:
            while max_iterations is None or iterations < max_iterations:
                self._run_once()
                iterations += 1
                if max_iterations is None or iterations < max_iterations:
                    time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Worker interrompido pelo usuário."))

    def _run_once(self) -> int:
        now = timezone.now()
        due_tasks = Task.objects.select_related("owner").defer("notes").pending_reminders(as_of=now)

        sent = 0
        for task in due_tasks:
            with transaction.atomic():
                if task.claim_reminder():
                    self._notify(task, now)
                    sent += 1

        if sent:
            self.stdout.write(self.style.SUCCESS(f"{sent} lembrete(s) disparado(s)."))
        else:
            self.stdout.write("Nenhum lembrete pendente.")

        return sent

    def _notify(self, task: Task, now) -> None:
        self.stdout.write(
            f'🔔 Lembrete: "{task.title}" (usuário {task.owner.username}) '
            f"agendada para {timezone.localtime(task.scheduled_for)} "
            f"— verificado em {timezone.localtime(now)}."
        )
