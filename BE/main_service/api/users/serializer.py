from rest_framework import serializers
from .models import User, UserDetails, CompanyDetails

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'  # Include all fields of the User model
        # fields = ['id', 'email', 'password']

class UserDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDetails
        fields = '__all__'  # Include all fields of the UserDetails model

class CompanyDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyDetails
        fields = '__all__'  # Include all fields of the CompanyDetails model
