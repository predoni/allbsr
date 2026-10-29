from django.db import models
import uuid

# Create your models here.
class User(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=100)
    is_company = models.BooleanField(default=False)
    details = models.OneToOneField('UserDetails', on_delete=models.CASCADE, null=True, blank=True)
    company_details = models.OneToOneField('CompanyDetails', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.email

class UserDetails(models.Model):
    #user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='details')
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class CompanyDetails(models.Model):
    #user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='company_details')
    company_name = models.CharField(max_length=255)
    company_address = models.TextField(blank=True, null=True)
    company_phone_number = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return self.company_name