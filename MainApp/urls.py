from django.urls import path
from MainApp import views
urlpatterns = [
    path('', views.HomeView, name="home"),
    path('login', views.loginView, name="login")
]
