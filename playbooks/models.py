from django.db import models


class PlaybookChunk(models.Model):
    source_name = models.CharField(max_length=255)
    chunk_text  = models.TextField()
    clause_type = models.CharField(max_length=100)
    chroma_id   = models.CharField(max_length=100, unique=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['source_name', 'clause_type']

    def __str__(self):
        return f'{self.source_name} — {self.clause_type}'