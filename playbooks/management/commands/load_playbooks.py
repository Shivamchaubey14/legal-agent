from django.core.management.base import BaseCommand
from playbooks.loader import load_all_playbooks, validate_retrieval


class Command(BaseCommand):
    help = 'Load legal playbook data into ChromaDB and validate retrieval quality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action  = 'store_true',
            default = False,
            help    = 'Clear existing playbook embeddings before loading',
        )
        parser.add_argument(
            '--validate',
            action  = 'store_true',
            default = False,
            help    = 'Run retrieval validation after loading',
        )

    def handle(self, *args, **options):
        self.stdout.write('\n── Loading playbooks into ChromaDB ──\n')

        result = load_all_playbooks(reset=options['reset'])

        if not result['success']:
            self.stdout.write(
                self.style.ERROR(f"Failed: {result.get('error')}")
            )
            return

        self.stdout.write(self.style.SUCCESS(
            f"✓ Loaded {len(result['files_loaded'])} files "
            f"→ {result['total_chunks']} chunks"
        ))

        for f in result['files_loaded']:
            self.stdout.write(f"  · {f}")

        if options['validate']:
            self.stdout.write('\n── Validating retrieval quality ──\n')
            val = validate_retrieval()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Accuracy: {val['accuracy']} ({val['accuracy_pct']}%)"
                )
            )
            self.stdout.write('')

            for r in val['results']:
                status = '✓' if r['hit'] else '✗'
                color  = self.style.SUCCESS if r['hit'] else self.style.ERROR
                self.stdout.write(color(
                    f"  {status} [{r['expected_type']:20}] {r['query']}"
                ))
                if not r['hit']:
                    self.stdout.write(
                        f"      got: {r['got_types']}"
                    )