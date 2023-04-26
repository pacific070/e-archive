from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import render


class ProtectView(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        modulename = view_func.__module__
        user = request.user
        if user.is_authenticated:
            if modulename not in ['AdminApp.views', 'django.views.static'] and user.user_type == "Admin":
                return HttpResponseRedirect(reverse("dashboard"))
            elif modulename not in ['EmployeeApp.views', 'django.views.static'] and user.user_type == "Employee":
                return HttpResponseRedirect(reverse("employee_dashboard"))
        elif modulename not in ['MainApp.views', 'django.views.static']:
            return HttpResponseRedirect(reverse("login"))
