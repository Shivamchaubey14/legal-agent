from django.db import models
from django.contrib.auth.models import User


class Contract(models.Model):

    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('processing', 'Processing'),
        ('done',       'Done'),
        ('error',      'Error'),
    ]

    RISK_CHOICES = [
        ('low',      'Low'),
        ('medium',   'Medium'),
        ('high',     'High'),
        ('critical', 'Critical'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contracts')
    title      = models.CharField(max_length=255)
    file_path  = models.CharField(max_length=500, blank=True)
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    page_count = models.IntegerField(default=0)
    raw_text   = models.TextField(blank=True)
    risk_score = models.CharField(max_length=20, choices=RISK_CHOICES, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} — {self.user.username}"