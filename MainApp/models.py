from django.db import models
from django.utils.translation import gettext_lazy as _
from .utils import getId, generate_ticket_no, convert_hour
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from .modelManager import CustomUserManager
import os

DOCUMENTS_SELECT_RELATED = "'issue_type', 'assign_engineer', 'assigned_by', 'resolved_by', 'rejected_by'"
ISSUE_TYPES_SELECT_RELATED = "department"
EMPLOYEE_SELECT_RELATED = "'department', 'auth'"
ENGINEER_SELECT_RELATED = "'department', 'auth'"


USER_TYPE_CHOICES = [
    ('Admin', "ADMIN"), ('Employee', "EMPLOYEE")
]

DOCUMENT_STATUS_CHOICES = [
    ('Pending', "PENDING"),
    ('Rejected', "REJECTED"),
    ('Approved', "APPROVED")
]


class Department(models.Model):
    id = models.CharField(editable=False, primary_key=True, max_length=255)
    name = models.CharField(max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = getId('department_')
            while Department.objects.filter(id=self.id).exists():
                self.id = getId('dep_')
        super(Department, self).save()


class Category(models.Model):
    id = models.CharField(editable=False, primary_key=True, max_length=255)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    name = models.CharField(max_length=250)
    category_no = models.CharField(max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = getId('cat_')
            while Category.objects.filter(id=self.id).exists():
                self.id = getId('cat_')
        if not self.category_no:
            total = Category.objects.all().count()
            if total > 0:
                new_total = total + 100
                self.category_no = new_total
                while Category.objects.filter(category_no=self.category_no).exists():
                    new_total += 1
                    self.category_no = new_total
            else:
                self.category_no = 100
        super(Category, self).save()


class SubCategory(models.Model):
    id = models.CharField(editable=False, primary_key=True, max_length=255)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    name = models.CharField(max_length=250)
    sub_category_no = models.CharField(max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = getId('scat_')
            while SubCategory.objects.filter(id=self.id).exists():
                self.id = getId('scat_')

        if not self.sub_category_no:
            total = SubCategory.objects.all().count()
            if total > 0:
                new_total = total + 1000
                self.sub_category_no = new_total
                while SubCategory.objects.filter(sub_category_no=self.sub_category_no).exists():
                    new_total += 1
                    self.sub_category_no = new_total
            else:
                self.sub_category_no = 1000
        super(SubCategory, self).save()


class SubType(models.Model):
    id = models.CharField(editable=False, primary_key=True, max_length=255)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    name = models.CharField(max_length=250)
    subtype_no = models.CharField(max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = getId('subtp_')
            while SubType.objects.filter(id=self.id).exists():
                self.id = getId('subtp_')
        if not self.subtype_no:
            total = SubType.objects.all().count()
            if total > 0:
                new_total = total + 10000
                self.subtype_no = new_total
                while SubType.objects.filter(subtype_no=self.subtype_no).exists():
                    new_total += 1
                    self.subtype_no = new_total
            else:
                self.subtype_no = 10000
        super(SubType, self).save()


class Auth(AbstractBaseUser, PermissionsMixin):
    id = models.CharField(editable=False, primary_key=True, max_length=200)
    user_type = models.CharField(default=USER_TYPE_CHOICES[0][0],
                                 choices=USER_TYPE_CHOICES,
                                 max_length=10)
    email = models.EmailField(_('email address'), unique=True, null=True)
    name = models.CharField(max_length=50)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']
    objects = CustomUserManager()

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = getId('auth_')
            while Auth.objects.filter(id=self.id).exists():
                self.id = getId('auth_')
        super(Auth, self).save()


class Admin(models.Model):
    id = models.CharField(editable=False, primary_key=True, max_length=200)
    auth = models.OneToOneField(Auth, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = getId('admin_')
            while Admin.objects.filter(id=self.id).exists():
                self.id = getId('admin_')
        super(Admin, self).save()


class Employee(models.Model):
    id = models.CharField(editable=False, primary_key=True, max_length=200)
    auth = models.OneToOneField(Auth, on_delete=models.CASCADE)
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = getId('employee_')
            while Employee.objects.filter(id=self.id).exists():
                self.id = getId('employee_')
        super(Employee, self).save()


def UploadedConfigPath(instance, filename):
    return os.path.join(instance.sub_path, filename)


class UploadMedia(models.Model):
    id = models.CharField(editable=False, primary_key=True, max_length=200)
    file_name = models.TextField(blank=True)
    file_size = models.IntegerField(blank=True)
    content_type = models.CharField(max_length=200, blank=True)
    sub_path = models.CharField(max_length=200, default="chat")
    is_used = models.BooleanField(default=True)
    file = models.FileField(upload_to=UploadedConfigPath)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = getId("media_")
            while UploadMedia.objects.filter(id=self.id).exists():
                self.id = getId("media_")
        super(UploadMedia, self).save()


class Documents(models.Model):
    id = models.CharField(editable=False, primary_key=True, max_length=255)
    sub_category = models.ForeignKey(SubCategory, on_delete=models.CASCADE)
    subtype = models.ForeignKey(SubType, on_delete=models.CASCADE)
    status = models.CharField(
        default=DOCUMENT_STATUS_CHOICES[0][0], choices=DOCUMENT_STATUS_CHOICES, max_length=15)
    media = models.ForeignKey(UploadMedia, on_delete=models.CASCADE)
    document_no = models.CharField(max_length=250)
    version = models.CharField(max_length=250, default='v1')
    description = models.TextField()

    upload_by = models.ForeignKey(
        Auth, on_delete=models.SET_NULL, null=True, related_name='upload_by')
    upload_on = models.DateTimeField()

    modify_by = models.ForeignKey(
        Auth, on_delete=models.SET_NULL, null=True, related_name='modify_by')
    modify_on = models.DateTimeField()

    rejected_reason = models.TextField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = getId('issue_')
            while Documents.objects.filter(id=self.id).exists():
                self.id = getId('doc_')
        if not self.document_no:
            total = Documents.objects.all().count()
            if total > 0:
                new_total = total + 100000
                self.document_no = new_total
                while Documents.objects.filter(document_no=self.document_no).exists():
                    new_total += 1
                    self.document_no = new_total
            else:
                self.document_no = 100000
        super(Documents, self).save()


@receiver(post_save, sender=Auth)
def create_user_data(sender, instance, created, **kwargs):
    if created:
        if instance.user_type == USER_TYPE_CHOICES[0][0]:
            Admin.objects.create(auth=instance)
        if instance.user_type == USER_TYPE_CHOICES[1][0]:
            Employee.objects.create(auth=instance)


@receiver(post_save, sender=Auth)
def save_user_data(sender, instance, **kwargs):
    if instance.user_type == USER_TYPE_CHOICES[0][0]:
        instance.admin.save()
    if instance.user_type == USER_TYPE_CHOICES[1][0]:
        instance.employee.save()
