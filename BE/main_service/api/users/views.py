from django.shortcuts import render
from rest_framework import viewsets
from .serializer import UserSerializer, UserDetailsSerializer, CompanyDetailsSerializer
from .models import User, UserDetails, CompanyDetails

# Create your views here.

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class UserDetailsViewSet(viewsets.ModelViewSet):
    queryset = UserDetails.objects.all()
    serializer_class = UserDetailsSerializer

class CompanyDetailsViewSet(viewsets.ModelViewSet):
    queryset = CompanyDetails.objects.all()
    serializer_class = CompanyDetailsSerializer