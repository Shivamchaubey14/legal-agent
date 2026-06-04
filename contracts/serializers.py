from rest_framework import serializers
from .models import Contract, ClauseFlag
import os


class ContractSerializer(serializers.ModelSerializer):
    user     = serializers.StringRelatedField(read_only=True)
    duration = serializers.SerializerMethodField()
    risk_score_value = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Contract
        fields = [
            'id', 'user', 'title', 'file_path', 'status',
            'page_count', 'risk_score', 'risk_score_value',
            'created_at', 'duration',
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

    def validate_title(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError('Title must be at least 2 characters.')
        if len(value) > 255:
            raise serializers.ValidationError('Title cannot exceed 255 characters.')
        return value


class ContractUploadSerializer(serializers.Serializer):
    """Used to validate the upload request before saving."""
    file  = serializers.FileField()
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)

    ALLOWED_EXTENSIONS = {'.pdf', '.docx'}
    MAX_SIZE_MB        = 20
    MAX_SIZE_BYTES     = MAX_SIZE_MB * 1024 * 1024

    def validate_file(self, file):
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f'"{ext}" is not supported. Please upload a PDF or DOCX file.'
            )
        if file.size > self.MAX_SIZE_BYTES:
            size_mb = round(file.size / (1024 * 1024), 1)
            raise serializers.ValidationError(
                f'File is {size_mb} MB. Maximum allowed size is {self.MAX_SIZE_MB} MB.'
            )
        if file.size == 0:
            raise serializers.ValidationError('The uploaded file is empty.')
        return file

    def validate_title(self, value):
        return value.strip()[:255]


class ClauseFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ClauseFlag
        fields = [
            'id', 'clause_type', 'clause_text', 'risk_level',
            'reason', 'suggestion', 'redline', 'page_number', 'created_at',
        ]