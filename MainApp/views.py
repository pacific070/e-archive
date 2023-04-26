from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth import login as log_in
from MainApp.models import Auth
from .CustomAuthentication import AuthBackend


def HomeView(request):  # sourcery skip: last-if-guard
    return render(request, 'MainApp/index.html')

def loginView(request):  # sourcery skip: last-if-guard
    if request.method == "POST":
        try:
            email = request.POST.get("email", None)
            password = request.POST.get("password", None)

            if not email:
                messages.error(request, "Required Email")
                return HttpResponseRedirect(reverse('login'))
            if not password:
                messages.error(request, "Required Password")
                return HttpResponseRedirect(reverse('login'))
            if not Auth.objects.filter(email=email).exists():
                messages.error(request, "Email not found!")
                return HttpResponseRedirect(reverse('login'))
            if user := AuthBackend.authenticate(request, email, password):
                log_in(request, user)
                if user.user_type == "Admin":
                    return HttpResponseRedirect(reverse('dashboard'))
                elif user.user_type == "Employee":
                    return HttpResponseRedirect(reverse('employee_dashboard'))
                else:
                    return HttpResponseRedirect(reverse('login'))
            messages.error(request, "Invalid Password")
            return HttpResponseRedirect(reverse('login'))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse('login'))
    else:
        return render(request, 'MainApp/login.html')
