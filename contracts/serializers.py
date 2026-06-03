from rest_framework import serializers
from .models import Contract, ClauseFlag


class ContractSerializer(serializers.ModelSerializer):
    user     = serializers.StringRelatedField(read_only=True)
    duration = serializers.SerializerMethodField()

    class Meta:
        model  = Contract
        fields = [
            'id', 'user', 'title', 'file_path', 'status',
            'page_count', 'risk_score', 'created_at', 'duration',
        ]
        read_only_fields = ['id', 'user', 'created_at']

    def get_duration(self, obj):
        from django.utils.timezone import now
        diff = now() - obj.created_at
        days = diff.days
        if days == 0:
            hours = diff.seconds // 3600
            if hours == 0:
                mins = diff.seconds // 60
                return f"{mins}m ago"
            return f"{hours}h ago"
        if days < 30:
            return f"{days}d ago"
        return obj.created_at.strftime("%b %d, %Y")
    

class ClauseFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ClauseFlag   
        fields = [
    'id', 'clause_type', 'clause_text', 'risk_level',
    'reason', 'suggestion', 'redline', 'page_number', 'created_at',
]