"""Worker de lembretes.

Um processo simples de *polling* que consulta periodicamente o banco
(via Django ORM — sem fila externa, sem Redis/Celery: só Postgres) por
tarefas cujo lembrete já deveria ter disparado, e as marca como
notificadas.

IMPORTANTE — o que este worker faz e o que ele NÃO faz:
- Ele identifica corretamente quais tarefas têm lembrete pendente e
  registra que o aviso foi disparado (`Task.reminder_sent_at`).
- Ele NÃO envia e-mail, push ou SMS de fato — o "disparo" aqui é uma
  linha de log (stdout). Ligar isso a um canal real de notificação é
  uma troca de uma função (`_notify`), mas exigiria credenciais de
  e-mail/push configuradas, o que ficou fora do escopo pedido (rodar
  só com Postgres, sem outra infraestrutura).

Uso:
    python manage.py send_reminders                  # uma passada e sai
    python manage.py send_reminders --loop            # roda continuamente
    python manage.py send_reminders --loop --interval 15
    python manage.py send_reminders --loop --max-iterations 3   # uso em testes
"""

import time

from django.core.management.base import BaseCommand
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
        due_tasks = Task.objects.pending_reminders(as_of=now)

        for task in due_tasks:
            self._notify(task, now)
            task.mark_reminder_sent()

        if due_tasks:
            self.stdout.write(
                self.style.SUCCESS(f"{len(due_tasks)} lembrete(s) disparado(s).")
            )
        else:
            self.stdout.write("Nenhum lembrete pendente.")

        return len(due_tasks)

    def _notify(self, task: Task, now) -> None:
        """Ponto único de disparo do aviso. Hoje só loga; troque aqui para
        integrar e-mail/push/SMS real no futuro.
        """
        self.stdout.write(
            f'🔔 Lembrete: "{task.title}" (usuário {task.owner.username}) '
            f"agendada para {timezone.localtime(task.scheduled_for)} "
            f"— verificado em {timezone.localtime(now)}."
        )
