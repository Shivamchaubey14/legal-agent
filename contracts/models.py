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
    
    
class ClauseFlag(models.Model):
    RISK_LEVELS = [
        ('low',      'Low'),
        ('medium',   'Medium'),
        ('high',     'High'),
        ('critical', 'Critical'),
    ]

    contract    = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='flags')
    clause_type = models.CharField(max_length=100)
    clause_text = models.TextField()
    risk_level  = models.CharField(max_length=20, choices=RISK_LEVELS)
    reason      = models.TextField()
    suggestion  = models.TextField()
    page_number = models.IntegerField(default=0)
    start_char  = models.IntegerField(default=0)
    end_char    = models.IntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-risk_level', 'clause_type']

    def __str__(self):
        return f'{self.contract.title} — {self.clause_type} [{self.risk_level}]'