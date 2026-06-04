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
    risk_score_value = models.IntegerField(default=0)  # 0-100 numeric score
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} — {self.user.username}"
    
    
class ClauseFlag(models.Model):

    RISK_CHOICES = [
        ('low',    'Low'),
        ('medium', 'Medium'),
        ('high',   'High'),
    ]

    redline = models.TextField(blank=True, default='')
    contract    = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='clause_flags')
    clause_type = models.CharField(max_length=100)
    clause_text = models.TextField()
    risk_level  = models.CharField(max_length=20, choices=RISK_CHOICES, default='medium')
    reason      = models.TextField()
    suggestion  = models.TextField()
    page_number = models.IntegerField(default=1)
    start_char  = models.IntegerField(default=0)
    end_char    = models.IntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-risk_level', 'clause_type']

    def __str__(self):
        return f'{self.clause_type} ({self.risk_level}) — Contract {self.contract_id}'
    

class ChatSession(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='chat_sessions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_sessions')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f'Session for {self.contract.title} by {self.user.username}'
    
class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    citations = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        
    def __str__(self):
        return f'[{self.role}] {self.content[:60]}'