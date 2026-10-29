from django.contrib.auth.hashers import make_password
from django.db import transaction
from rest_framework import serializers
from .models import CompanyDetails, PasswordResetToken, User, UserDetails

class UserDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDetails
        fields = '__all__'  # Include all fields of the UserDetails model


class CompanyDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyDetails
        fields = '__all__'  # Include all fields of the CompanyDetails model


class UserSerializer(serializers.ModelSerializer):
    # Nested: the client sends/receives the details as an object, not as an id.
    #   {"email": ..., "password": ..., "details": {"first_name": ..., "last_name": ...}}
    details = UserDetailsSerializer(required=False, allow_null=True)
    company_details = CompanyDetailsSerializer(required=False, allow_null=True)

    class Meta:
        model = User
        fields = '__all__'  # Include all fields of the User model
        # write_only: accepted on POST/PUT/PATCH, but never included in responses
        extra_kwargs = {'password': {'write_only': True}}
        read_only_fields = ['is_admin']  # shown in responses, ignored on input

    # DRF refuses to guess how to save nested objects, so we say so explicitly.
    # transaction.atomic: if anything below fails, nothing is written (no orphans).

    @transaction.atomic
    def create(self, validated_data):
        details_data = validated_data.pop('details', None)
        company_data = validated_data.pop('company_details', None)

        validated_data['password'] = make_password(validated_data['password'])
        validated_data['details'] = self._save_nested(UserDetails, None, details_data)
        validated_data['company_details'] = self._save_nested(CompanyDetails, None, company_data)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        # Only re-hash if the client actually sent a new password (PATCH may omit it)
        if 'password' in validated_data:
            validated_data['password'] = make_password(validated_data['password'])

        # `in` rather than .get(): an explicit null means "remove", absent means "leave alone"
        if 'details' in validated_data:
            validated_data['details'] = self._save_nested(
                UserDetails, instance.details, validated_data['details']
            )
        if 'company_details' in validated_data:
            validated_data['company_details'] = self._save_nested(
                CompanyDetails, instance.company_details, validated_data['company_details']
            )
        return super().update(instance, validated_data)

    @staticmethod
    def _save_nested(model, existing, data):
        """Create, update in place, or (if data is None) delete a nested details row."""
        if data is None:
            if existing is not None:
                existing.delete()
            return None
        if existing is None:
            return model.objects.create(**data)
        for field, value in data.items():
            setattr(existing, field, value)
        existing.save()
        return existing




class LoginSerializer(serializers.Serializer):
    """Not a ModelSerializer: it validates credentials rather than creating rows."""
    # CharField, not EmailField: it's only a lookup key, and the seeded admin
    # account's identifier is the plain word "admin".
    email = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = User.objects.filter(email=attrs['email']).first()
        # Deliberately the same error for "no such user" and "wrong password",
        # so the login form can't be used to discover registered emails.
        if user is None or not user.check_password(attrs['password']):
            raise serializers.ValidationError('Invalid email or password.')
        attrs['user'] = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.CharField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_token(self, key):
        # validate_<field> runs for just that field; errors land under its name.
        token = PasswordResetToken.objects.select_related('user').filter(key=key).first()
        if token is None or not token.is_valid:
            raise serializers.ValidationError('Invalid or expired token.')
        return token  # the view receives the model instance, not the raw string
